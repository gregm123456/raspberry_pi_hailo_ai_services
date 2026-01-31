#!/usr/bin/env python3
"""
Hailo Face Recognition Service - Face Detection and Recognition REST API.

Exposes face recognition model as a systemd service with REST endpoints for:
- Face detection (bounding boxes)
- Face embedding extraction
- Face recognition (compare against database)
- Database management (add/remove/list identities)
"""

import base64
import json
import logging
import os
import signal
import sqlite3
import sys
import threading
import time
import traceback
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
import yaml
from flask import Flask, jsonify, request
from PIL import Image

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("hailo-face-service")


class FaceServiceConfig:
    """Load and validate Face Recognition service configuration."""
    
    def __init__(self, yaml_path: str = "/etc/hailo/hailo-face.yaml"):
        self.yaml_path = yaml_path
        self.config: Dict[str, Any] = {}
        self.load()
    
    def load(self) -> None:
        """Load configuration from YAML."""
        try:
            with open(self.yaml_path, "r", encoding="utf-8") as f:
                self.config = yaml.safe_load(f) or {}
            
            logger.info(f"Loaded config from {self.yaml_path}")
        except FileNotFoundError:
            logger.warning(f"Config file not found: {self.yaml_path}, using defaults")
            self.config = self._defaults()
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            self.config = self._defaults()
    
    def _defaults(self) -> Dict[str, Any]:
        """Return default configuration."""
        return {
            "server": {"host": "0.0.0.0", "port": 5002, "debug": False},
            "face_recognition": {
                "detection_model": "scrfd_10g",
                "recognition_model": "arcface_mobilefacenet",
                "embedding_dimension": 512,
                "device": 0,
                "detection_threshold": 0.6,
                "recognition_threshold": 0.5,
                "max_faces": 10,
                "database_path": "/var/lib/hailo-face/database",
            },
            "database": {
                "enabled": True,
                "db_file": "/var/lib/hailo-face/faces.db",
            },
            "performance": {
                "worker_threads": 2,
                "request_timeout": 30,
            },
        }
    
    @property
    def server(self) -> Dict[str, Any]:
        return self.config.get("server", {})
    
    @property
    def face_recognition(self) -> Dict[str, Any]:
        return self.config.get("face_recognition", {})
    
    @property
    def database(self) -> Dict[str, Any]:
        return self.config.get("database", {})
    
    @property
    def performance(self) -> Dict[str, Any]:
        return self.config.get("performance", {})


class FaceDatabase:
    """SQLite database for storing face embeddings and identities."""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.lock = threading.RLock()
        self._init_db()
    
    def _init_db(self) -> None:
        """Initialize database schema."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Table for identities
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS identities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Table for embeddings (multiple per identity)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS embeddings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    identity_id INTEGER NOT NULL,
                    embedding BLOB NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (identity_id) REFERENCES identities(id) ON DELETE CASCADE
                )
            """)
            
            # Index for faster lookups
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_embeddings_identity 
                ON embeddings(identity_id)
            """)
            
            conn.commit()
            conn.close()
        
        logger.info(f"Initialized face database: {self.db_path}")
    
    def add_identity(self, name: str, embedding: np.ndarray) -> bool:
        """Add a new identity with embedding."""
        with self.lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                # Insert or get identity
                cursor.execute(
                    "INSERT OR IGNORE INTO identities (name) VALUES (?)",
                    (name,)
                )
                cursor.execute("SELECT id FROM identities WHERE name = ?", (name,))
                identity_id = cursor.fetchone()[0]
                
                # Store embedding as binary blob
                embedding_blob = embedding.astype(np.float32).tobytes()
                cursor.execute(
                    "INSERT INTO embeddings (identity_id, embedding) VALUES (?, ?)",
                    (identity_id, embedding_blob)
                )
                
                conn.commit()
                conn.close()
                logger.info(f"Added embedding for identity: {name}")
                return True
                
            except Exception as e:
                logger.error(f"Failed to add identity: {e}")
                return False
    
    def remove_identity(self, name: str) -> bool:
        """Remove an identity and all its embeddings."""
        with self.lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                cursor.execute("DELETE FROM identities WHERE name = ?", (name,))
                deleted = cursor.rowcount > 0
                
                conn.commit()
                conn.close()
                
                if deleted:
                    logger.info(f"Removed identity: {name}")
                return deleted
                
            except Exception as e:
                logger.error(f"Failed to remove identity: {e}")
                return False
    
    def list_identities(self) -> List[Dict[str, Any]]:
        """List all identities with embedding counts."""
        with self.lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT i.name, COUNT(e.id) as embedding_count, i.created_at
                    FROM identities i
                    LEFT JOIN embeddings e ON i.id = e.identity_id
                    GROUP BY i.id, i.name, i.created_at
                    ORDER BY i.name
                """)
                
                results = []
                for row in cursor.fetchall():
                    results.append({
                        "name": row[0],
                        "embedding_count": row[1],
                        "created_at": row[2],
                    })
                
                conn.close()
                return results
                
            except Exception as e:
                logger.error(f"Failed to list identities: {e}")
                return []
    
    def find_match(self, query_embedding: np.ndarray, threshold: float = 0.5) -> Optional[Tuple[str, float]]:
        """
        Find best matching identity for query embedding.
        
        Returns:
            Tuple of (identity_name, similarity_score) or None if no match above threshold
        """
        with self.lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                # Get all embeddings
                cursor.execute("""
                    SELECT i.name, e.embedding
                    FROM embeddings e
                    JOIN identities i ON e.identity_id = i.id
                """)
                
                best_match = None
                best_score = threshold
                
                for name, embedding_blob in cursor.fetchall():
                    # Deserialize embedding
                    stored_embedding = np.frombuffer(embedding_blob, dtype=np.float32)
                    
                    # Compute cosine similarity
                    similarity = self._cosine_similarity(query_embedding, stored_embedding)
                    
                    if similarity > best_score:
                        best_score = similarity
                        best_match = name
                
                conn.close()
                
                if best_match:
                    return (best_match, float(best_score))
                return None
                
            except Exception as e:
                logger.error(f"Failed to find match: {e}")
                return None
    
    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """Compute cosine similarity between two vectors."""
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))


class FaceRecognitionModel:
    """Wrapper for Hailo-accelerated face detection and recognition models."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.detection_model = None
        self.recognition_model = None
        self.is_loaded = False
        self.lock = threading.RLock()
        
        self.detection_model_name = config.get("detection_model", "scrfd_10g")
        self.recognition_model_name = config.get("recognition_model", "arcface_mobilefacenet")
        self.device = config.get("device", 0)
        self.detection_threshold = config.get("detection_threshold", 0.6)
        self.max_faces = config.get("max_faces", 10)
        self.embedding_dim = config.get("embedding_dimension", 512)
        
        logger.info(
            f"FaceRecognitionModel initialized: detection={self.detection_model_name}, "
            f"recognition={self.recognition_model_name}, device={self.device}"
        )
    
    def load(self) -> bool:
        """Load face detection and recognition models from hailo-apps."""
        with self.lock:
            if self.is_loaded:
                return True
            
            try:
                # Try importing from hailo-apps
                logger.info("Loading face recognition models...")
                
                # For now, use a mock model
                # In production, this would import from hailo-apps face_recognition pipeline
                logger.warning("Using mock face recognition model (hailo-apps integration pending)")
                self._use_mock_model()
                return True
                
            except Exception as e:
                logger.error(f"Failed to load face models: {e}")
                traceback.print_exc()
                return False
    
    def _use_mock_model(self) -> None:
        """Use a mock model for development/testing."""
        self.detection_model = None
        self.recognition_model = None
        self.is_loaded = True
        logger.info("Mock face recognition model loaded")
    
    def detect_faces(self, image: Image.Image) -> List[Dict[str, Any]]:
        """
        Detect faces in an image.
        
        Returns:
            List of face detections with bounding boxes and confidence scores
        """
        if not self.is_loaded:
            logger.error("Model not loaded")
            return []
        
        try:
            with self.lock:
                # Convert to numpy array
                image_array = np.array(image)
                
                if self.detection_model is None:
                    # Mock detection: return random boxes
                    height, width = image_array.shape[:2]
                    num_faces = min(np.random.randint(1, 4), self.max_faces)
                    
                    faces = []
                    for i in range(num_faces):
                        x = np.random.randint(0, width // 2)
                        y = np.random.randint(0, height // 2)
                        w = np.random.randint(width // 4, width // 2)
                        h = np.random.randint(height // 4, height // 2)
                        
                        faces.append({
                            "bbox": [int(x), int(y), int(w), int(h)],
                            "confidence": float(np.random.uniform(0.7, 0.99)),
                            "landmarks": None,  # Optional 5-point landmarks
                        })
                    
                    return faces
                
                # Real model inference would go here
                # Use hailo-apps face detection pipeline
                return []
                
        except Exception as e:
            logger.error(f"Failed to detect faces: {e}")
            traceback.print_exc()
            return []
    
    def extract_embedding(self, image: Image.Image, bbox: List[int]) -> Optional[np.ndarray]:
        """
        Extract face embedding from cropped face region.
        
        Args:
            image: PIL Image
            bbox: [x, y, width, height]
            
        Returns:
            Embedding array or None on error
        """
        if not self.is_loaded:
            logger.error("Model not loaded")
            return None
        
        try:
            with self.lock:
                # Crop face region
                x, y, w, h = bbox
                image_array = np.array(image)
                face_crop = image_array[y:y+h, x:x+w]
                
                if face_crop.size == 0:
                    logger.error("Invalid face crop")
                    return None
                
                if self.recognition_model is None:
                    # Mock embedding: return random normalized vector
                    embedding = np.random.randn(self.embedding_dim).astype(np.float32)
                    embedding = embedding / (np.linalg.norm(embedding) + 1e-8)
                    return embedding
                
                # Real model inference would go here
                # Use hailo-apps arcface model
                return None
                
        except Exception as e:
            logger.error(f"Failed to extract embedding: {e}")
            traceback.print_exc()
            return None


def create_app(config: FaceServiceConfig) -> Flask:
    """Create and configure Flask application."""
    app = Flask(__name__)
    
    # Initialize face recognition model
    face_model = FaceRecognitionModel(config.face_recognition)
    if not face_model.load():
        logger.error("Failed to initialize face recognition model")
        sys.exit(1)
    
    # Initialize face database
    db_enabled = config.database.get("enabled", True)
    db_path = config.database.get("db_file", "/var/lib/hailo-face/faces.db")
    face_db = FaceDatabase(db_path) if db_enabled else None
    
    @app.route("/health", methods=["GET"])
    def health() -> Tuple[Dict[str, Any], int]:
        """Health check endpoint."""
        return jsonify({
            "status": "healthy",
            "service": "hailo-face",
            "model_loaded": face_model.is_loaded,
            "detection_model": face_model.detection_model_name,
            "recognition_model": face_model.recognition_model_name,
            "database_enabled": db_enabled,
        }), 200
    
    @app.route("/v1/detect", methods=["POST"])
    def detect_faces() -> Tuple[Dict[str, Any], int]:
        """
        Detect faces in an image.
        
        Request body (JSON):
        {
            "image": "data:image/jpeg;base64,...",
            "return_landmarks": false
        }
        
        Response:
        {
            "faces": [
                {
                    "bbox": [x, y, width, height],
                    "confidence": 0.95,
                    "landmarks": [[x1, y1], [x2, y2], ...] (optional)
                }
            ],
            "count": 2,
            "inference_time_ms": 45
        }
        """
        try:
            data = request.get_json()
            if not data:
                return jsonify({"error": "No JSON body"}), 400
            
            # Decode image
            image = _decode_image(data)
            if image is None:
                return jsonify({"error": "Failed to decode image"}), 400
            
            # Detect faces
            start_time = time.time()
            faces = face_model.detect_faces(image)
            inference_time_ms = (time.time() - start_time) * 1000
            
            return jsonify({
                "faces": faces,
                "count": len(faces),
                "inference_time_ms": inference_time_ms,
            }), 200
            
        except Exception as e:
            logger.error(f"Detect faces error: {e}")
            traceback.print_exc()
            return jsonify({"error": str(e)}), 500
    
    @app.route("/v1/embed", methods=["POST"])
    def embed_face() -> Tuple[Dict[str, Any], int]:
        """
        Extract face embedding from an image.
        
        Request body:
        {
            "image": "data:image/jpeg;base64,...",
            "bbox": [x, y, width, height]  (optional, will auto-detect if omitted)
        }
        
        Response:
        {
            "embedding": [0.1, 0.2, ...],
            "dimension": 512,
            "bbox": [x, y, w, h]
        }
        """
        try:
            data = request.get_json()
            if not data:
                return jsonify({"error": "No JSON body"}), 400
            
            # Decode image
            image = _decode_image(data)
            if image is None:
                return jsonify({"error": "Failed to decode image"}), 400
            
            # Get or detect bbox
            bbox = data.get("bbox")
            if bbox is None:
                # Auto-detect first face
                faces = face_model.detect_faces(image)
                if not faces:
                    return jsonify({"error": "No face detected"}), 400
                bbox = faces[0]["bbox"]
            
            # Extract embedding
            embedding = face_model.extract_embedding(image, bbox)
            if embedding is None:
                return jsonify({"error": "Failed to extract embedding"}), 500
            
            return jsonify({
                "embedding": embedding.tolist(),
                "dimension": len(embedding),
                "bbox": bbox,
            }), 200
            
        except Exception as e:
            logger.error(f"Embed face error: {e}")
            return jsonify({"error": str(e)}), 500
    
    @app.route("/v1/recognize", methods=["POST"])
    def recognize_faces() -> Tuple[Dict[str, Any], int]:
        """
        Recognize faces in an image against database.
        
        Request body:
        {
            "image": "data:image/jpeg;base64,...",
            "threshold": 0.5  (optional)
        }
        
        Response:
        {
            "faces": [
                {
                    "bbox": [x, y, w, h],
                    "identity": "John Doe",
                    "confidence": 0.85,
                    "match_score": 0.92
                }
            ],
            "inference_time_ms": 120
        }
        """
        if not db_enabled:
            return jsonify({"error": "Database not enabled"}), 503
        
        try:
            data = request.get_json()
            if not data:
                return jsonify({"error": "No JSON body"}), 400
            
            # Decode image
            image = _decode_image(data)
            if image is None:
                return jsonify({"error": "Failed to decode image"}), 400
            
            threshold = data.get("threshold", face_model.config.get("recognition_threshold", 0.5))
            
            # Detect and recognize faces
            start_time = time.time()
            detected_faces = face_model.detect_faces(image)
            
            recognized_faces = []
            for face in detected_faces:
                bbox = face["bbox"]
                embedding = face_model.extract_embedding(image, bbox)
                
                if embedding is not None:
                    match = face_db.find_match(embedding, threshold)
                    
                    recognized_faces.append({
                        "bbox": bbox,
                        "detection_confidence": face["confidence"],
                        "identity": match[0] if match else "Unknown",
                        "match_score": match[1] if match else 0.0,
                    })
            
            inference_time_ms = (time.time() - start_time) * 1000
            
            return jsonify({
                "faces": recognized_faces,
                "count": len(recognized_faces),
                "inference_time_ms": inference_time_ms,
            }), 200
            
        except Exception as e:
            logger.error(f"Recognize faces error: {e}")
            return jsonify({"error": str(e)}), 500
    
    @app.route("/v1/database/add", methods=["POST"])
    def add_identity() -> Tuple[Dict[str, Any], int]:
        """
        Add a new identity to the database.
        
        Request body:
        {
            "name": "John Doe",
            "image": "data:image/jpeg;base64,...",
            "bbox": [x, y, w, h]  (optional)
        }
        """
        if not db_enabled:
            return jsonify({"error": "Database not enabled"}), 503
        
        try:
            data = request.get_json()
            if not data or "name" not in data:
                return jsonify({"error": "Missing 'name' field"}), 400
            
            name = data["name"]
            
            # Decode image
            image = _decode_image(data)
            if image is None:
                return jsonify({"error": "Failed to decode image"}), 400
            
            # Get or detect bbox
            bbox = data.get("bbox")
            if bbox is None:
                faces = face_model.detect_faces(image)
                if not faces:
                    return jsonify({"error": "No face detected"}), 400
                bbox = faces[0]["bbox"]
            
            # Extract embedding
            embedding = face_model.extract_embedding(image, bbox)
            if embedding is None:
                return jsonify({"error": "Failed to extract embedding"}), 500
            
            # Add to database
            success = face_db.add_identity(name, embedding)
            if not success:
                return jsonify({"error": "Failed to add identity"}), 500
            
            return jsonify({
                "message": f"Identity '{name}' added successfully",
                "name": name,
            }), 200
            
        except Exception as e:
            logger.error(f"Add identity error: {e}")
            return jsonify({"error": str(e)}), 500
    
    @app.route("/v1/database/remove", methods=["POST"])
    def remove_identity() -> Tuple[Dict[str, Any], int]:
        """
        Remove an identity from the database.
        
        Request body: {"name": "John Doe"}
        """
        if not db_enabled:
            return jsonify({"error": "Database not enabled"}), 503
        
        try:
            data = request.get_json()
            if not data or "name" not in data:
                return jsonify({"error": "Missing 'name' field"}), 400
            
            name = data["name"]
            success = face_db.remove_identity(name)
            
            if not success:
                return jsonify({"error": f"Identity '{name}' not found"}), 404
            
            return jsonify({
                "message": f"Identity '{name}' removed successfully",
                "name": name,
            }), 200
            
        except Exception as e:
            logger.error(f"Remove identity error: {e}")
            return jsonify({"error": str(e)}), 500
    
    @app.route("/v1/database/list", methods=["GET"])
    def list_identities() -> Tuple[Dict[str, Any], int]:
        """
        List all identities in the database.
        
        Response:
        {
            "identities": [
                {"name": "John Doe", "embedding_count": 3, "created_at": "..."},
                ...
            ],
            "count": 2
        }
        """
        if not db_enabled:
            return jsonify({"error": "Database not enabled"}), 503
        
        try:
            identities = face_db.list_identities()
            return jsonify({
                "identities": identities,
                "count": len(identities),
            }), 200
            
        except Exception as e:
            logger.error(f"List identities error: {e}")
            return jsonify({"error": str(e)}), 500
    
    @app.errorhandler(404)
    def not_found(e) -> Tuple[Dict[str, Any], int]:
        return jsonify({"error": "Endpoint not found"}), 404
    
    @app.errorhandler(500)
    def internal_error(e) -> Tuple[Dict[str, Any], int]:
        return jsonify({"error": "Internal server error"}), 500
    
    return app


def _decode_image(data: Dict[str, Any]) -> Optional[Image.Image]:
    """
    Decode image from base64 or URL.
    
    Args:
        data: Request data dict with 'image' (base64) or 'image_url'
        
    Returns:
        PIL Image or None on error
    """
    try:
        if "image" in data:
            # Base64 encoded image
            b64_str = data["image"]
            if isinstance(b64_str, str) and b64_str.startswith("data:"):
                # Strip data URI prefix
                b64_str = b64_str.split(",", 1)[1]
            
            image_bytes = base64.b64decode(b64_str)
            image = Image.open(BytesIO(image_bytes))
            return image.convert("RGB")
        
        elif "image_url" in data:
            # URL-based image (mock for now)
            logger.warning("image_url not yet supported; use base64 image")
            return None
        
        else:
            logger.error("Neither 'image' nor 'image_url' in request")
            return None
            
    except Exception as e:
        logger.error(f"Failed to decode image: {e}")
        return None


def main():
    """Main entry point."""
    logger.info("Starting Hailo Face Recognition Service")
    
    # Load configuration
    config = FaceServiceConfig()
    
    # Create Flask app
    app = create_app(config)
    
    # Get server config
    host = config.server.get("host", "0.0.0.0")
    port = config.server.get("port", 5002)
    debug = config.server.get("debug", False)
    
    # Register signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down")
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    logger.info(f"Listening on {host}:{port}")
    
    try:
        app.run(host=host, port=port, debug=debug, threaded=True)
    except Exception as e:
        logger.error(f"Service error: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
