from __future__ import annotations

import base64
import io
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import gradio as gr
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image

from device_status_monitor import DeviceStatusMonitor
from status_formatters import (
    format_device_header,
    format_networks_table,
    create_temperature_gauge_html,
    create_queue_gauge_html,
)
from portal_client import (
    HailoClipClient,
    HailoDepthClient,
    HailoOllamaClient,
    HailoOCRClient,
    HailoPiperClient,
    HailoPoseClient,
    HailoVisionClient,
    HailoWhisperClient,
)
from service_manager import ServiceManager

monitor = DeviceStatusMonitor()
service_mgr = ServiceManager()

clip_client = HailoClipClient()
vision_client = HailoVisionClient()
whisper_client = HailoWhisperClient()
ocr_client = HailoOCRClient()
pose_client = HailoPoseClient()
depth_client = HailoDepthClient()
piper_client = HailoPiperClient()

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"])


@app.get("/api/status")
async def get_device_status() -> Dict[str, Any]:
    return monitor.get_status()


@app.get("/api/services/status")
async def get_services_status() -> Dict[str, str]:
    return await service_mgr.get_status()


@app.post("/api/services/start/{service_name}")
async def start_service(service_name: str) -> Dict[str, str]:
    return await service_mgr.start_service(service_name)


@app.post("/api/services/stop/{service_name}")
async def stop_service(service_name: str) -> Dict[str, str]:
    return await service_mgr.stop_service(service_name)


@app.post("/api/services/restart/{service_name}")
async def restart_service(service_name: str) -> Dict[str, str]:
    return await service_mgr.restart_service(service_name)


def build_gradio_interface() -> gr.Blocks:
    with gr.Blocks(
        title="Hailo AI Services Portal",
        theme=gr.themes.Soft(),
        css=(
            ".icon-button{width:36px !important;min-width:36px !important;max-width:36px !important;display:flex;align-items:center;justify-content:center;}"
            ".icon-button button{width:36px !important;min-width:36px !important;max-width:36px !important;height:36px !important;padding:0 !important;}"
        )
    ) as demo:
        gr.Markdown("# Hailo AI Services Portal")
        with gr.Row():
            with gr.Column(scale=0, min_width=40):
                refresh_status_btn = gr.Button(
                    "🔄", size="sm", elem_classes=["icon-button"]
                )
            with gr.Column(scale=1):
                device_info_md = gr.Markdown(
                    "Comprehensive testing interface for Hailo-10H AI services on Raspberry Pi 5."
                )

        # Temperature + Queue Gauges
        with gr.Row():
            with gr.Column(scale=0, min_width=200):
                temp_gauge = gr.HTML(label="Temperature")
            with gr.Column(scale=0, min_width=200):
                queue_info = gr.HTML(label="Queue")
            with gr.Column(scale=1):
                gr.HTML("")

        # Networks Table
        with gr.Accordion("Loaded Networks", open=True):
            networks_table = gr.Dataframe(
                headers=["Model Name", "Type", "Loaded At", "Last Used"],
                label=None,
                interactive=False,
                wrap=True,
            )

        def update_status() -> tuple:
            status_data = monitor.get_status()
            
            # Format device info for subtitle
            device_header = format_device_header(status_data)
            subtitle_text = (
                f"Comprehensive testing interface for Hailo-10H AI services on Raspberry Pi 5.  \n"
                f"**{device_header}**"
            )
            
            device = status_data.get("device", {})
            temp_c = device.get("temperature_celsius", 0)
            temp_gauge_html = create_temperature_gauge_html(temp_c)
            
            networks = format_networks_table(status_data)
            
            queue_depth = status_data.get("queue_depth", 0)
            queue_gauge_html = create_queue_gauge_html(queue_depth)
            
            return (subtitle_text, temp_gauge_html, networks, queue_gauge_html)

        refresh_status_btn.click(
            fn=update_status,
            outputs=[device_info_md, temp_gauge, networks_table, queue_info],
        )
        gr.Timer(3.0).tick(
            fn=update_status,
            outputs=[device_info_md, temp_gauge, networks_table, queue_info],
        )
        demo.load(
            fn=update_status,
            outputs=[device_info_md, temp_gauge, networks_table, queue_info],
        )

        with gr.Tabs():
            with gr.TabItem("CLIP"):
                gr.Markdown("### Zero-shot Classification and Embeddings")
                with gr.Tabs():
                    with gr.TabItem("Classify"):
                        with gr.Row():
                            with gr.Column():
                                clip_image = gr.Image(label="Upload Image", type="filepath")
                                clip_prompts = gr.Textbox(
                                    label="Text Prompts (one per line)",
                                    placeholder="a photo of a person\na photo of a dog",
                                    lines=5,
                                )
                                clip_top_k = gr.Slider(1, 10, value=3, step=1, label="Top K")
                                clip_threshold = gr.Slider(
                                    0.0, 1.0, value=0.0, step=0.05, label="Threshold"
                                )
                                clip_classify_btn = gr.Button("Classify", variant="primary")
                            with gr.Column():
                                clip_result = gr.JSON(label="Results")
                                clip_timing = gr.Textbox(label="Inference Time", interactive=False)

                        async def classify_image(
                            image: str, prompts_text: str, top_k: int, threshold: float
                        ) -> Tuple[Dict[str, Any], str]:
                            if not image or not prompts_text:
                                return {"error": "Missing image or prompts"}, ""
                            prompts = [p.strip() for p in prompts_text.split("\n") if p.strip()]
                            result = await clip_client.classify(image, prompts, int(top_k), threshold)
                            timing = f"{result.get('inference_time_ms', 0):.1f} ms"
                            return result, timing

                        clip_classify_btn.click(
                            fn=classify_image,
                            inputs=[clip_image, clip_prompts, clip_top_k, clip_threshold],
                            outputs=[clip_result, clip_timing],
                        )

                    with gr.TabItem("Image Embedding"):
                        with gr.Row():
                            with gr.Column():
                                clip_embed_image = gr.Image(label="Upload Image", type="filepath")
                                clip_embed_btn = gr.Button("Get Embedding", variant="primary")
                            with gr.Column():
                                clip_embed_result = gr.JSON(label="Embedding")
                                clip_embed_preview = gr.Textbox(
                                    label="First 10 Values", interactive=False
                                )

                        async def get_image_embedding(image: str) -> Tuple[Dict[str, Any], str]:
                            if not image:
                                return {"error": "Missing image"}, ""
                            result = await clip_client.embed_image(image)
                            preview = str(result.get("embedding", [])[:10])
                            return result, preview

                        clip_embed_btn.click(
                            fn=get_image_embedding,
                            inputs=[clip_embed_image],
                            outputs=[clip_embed_result, clip_embed_preview],
                        )

                    with gr.TabItem("Text Embedding"):
                        with gr.Row():
                            with gr.Column():
                                clip_text_input = gr.Textbox(
                                    label="Text",
                                    placeholder="a photo of a person wearing a red shirt",
                                    lines=3,
                                )
                                clip_text_embed_btn = gr.Button(
                                    "Get Embedding", variant="primary"
                                )
                            with gr.Column():
                                clip_text_embed_result = gr.JSON(label="Embedding")

                        async def get_text_embedding(text: str) -> Dict[str, Any]:
                            if not text:
                                return {"error": "Missing text"}
                            return await clip_client.embed_text(text)

                        clip_text_embed_btn.click(
                            fn=get_text_embedding,
                            inputs=[clip_text_input],
                            outputs=[clip_text_embed_result],
                        )

                    with gr.TabItem("Info"):
                        with gr.Row():
                            clip_health_btn = gr.Button("Health")
                        clip_health = gr.JSON(label="Health")

                        async def clip_health_info() -> Dict[str, Any]:
                            return await clip_client.health()

                        clip_health_btn.click(fn=clip_health_info, outputs=[clip_health])

            with gr.TabItem("Vision"):
                gr.Markdown("### Vision Language Model")
                with gr.Tabs():
                    with gr.TabItem("Chat"):
                        with gr.Row():
                            with gr.Column():
                                vision_image = gr.Image(label="Upload Image", type="filepath")
                                vision_prompt = gr.Textbox(
                                    label="Prompt",
                                    placeholder="Describe this image in detail.",
                                    lines=3,
                                )
                                with gr.Accordion("Advanced Options", open=False):
                                    vision_temperature = gr.Slider(
                                        0.0, 2.0, value=0.7, step=0.1, label="Temperature"
                                    )
                                    vision_max_tokens = gr.Slider(
                                        50, 500, value=200, step=50, label="Max Tokens"
                                    )
                                    vision_top_p = gr.Slider(
                                        0.0, 1.0, value=0.9, step=0.05, label="Top P"
                                    )
                                vision_chat_btn = gr.Button("Generate", variant="primary")
                            with gr.Column():
                                vision_response = gr.Textbox(
                                    label="Response", lines=10, interactive=False
                                )
                                vision_timing = gr.Textbox(
                                    label="Performance", interactive=False
                                )

                        async def vision_chat(
                            image: str, prompt: str, temp: float, max_tok: int, top_p: float
                        ) -> Tuple[str, str]:
                            if not image or not prompt:
                                return "Missing image or prompt", ""
                            result = await vision_client.chat_completions(
                                image, prompt, temp, int(max_tok), top_p
                            )
                            response_text = (
                                result.get("choices", [{}])[0]
                                .get("message", {})
                                .get("content", "")
                            )
                            timing = (
                                f"Inference: {result.get('performance', {}).get('inference_time_ms', 0):.1f} ms"
                            )
                            return response_text, timing

                        vision_chat_btn.click(
                            fn=vision_chat,
                            inputs=[
                                vision_image,
                                vision_prompt,
                                vision_temperature,
                                vision_max_tokens,
                                vision_top_p,
                            ],
                            outputs=[vision_response, vision_timing],
                        )

                    with gr.TabItem("Batch Analyze"):
                        with gr.Row():
                            with gr.Column():
                                vision_batch_images = gr.File(
                                    label="Upload Images", file_count="multiple", type="filepath"
                                )
                                vision_batch_prompt = gr.Textbox(
                                    label="Analysis Prompt",
                                    placeholder="For each image, describe the main objects.",
                                    lines=3,
                                )
                                vision_return_individual = gr.Checkbox(
                                    label="Return Individual Results", value=False
                                )
                                vision_batch_btn = gr.Button("Analyze", variant="primary")
                            with gr.Column():
                                vision_batch_result = gr.JSON(label="Batch Results")

                        async def vision_batch(
                            images: List[str],
                            prompt: str,
                            return_individual: bool,
                        ) -> Dict[str, Any]:
                            if not images or not prompt:
                                return {"error": "Missing images or prompt"}
                            return await vision_client.vision_analyze(
                                images,
                                prompt,
                                return_individual_results=return_individual,
                            )

                        vision_batch_btn.click(
                            fn=vision_batch,
                            inputs=[vision_batch_images, vision_batch_prompt, vision_return_individual],
                            outputs=[vision_batch_result],
                        )

                    with gr.TabItem("Info"):
                        vision_health_btn = gr.Button("Health")
                        vision_health = gr.JSON(label="Health")

                        async def vision_health_info() -> Dict[str, Any]:
                            return await vision_client.health()

                        vision_health_btn.click(fn=vision_health_info, outputs=[vision_health])

            with gr.TabItem("Whisper"):
                gr.Markdown("### Speech to Text")
                with gr.Tabs():
                    with gr.TabItem("Transcribe"):
                        with gr.Row():
                            with gr.Column():
                                whisper_audio = gr.Audio(label="Upload Audio", type="filepath")
                                whisper_language = gr.Dropdown(
                                    [
                                        "Auto",
                                        "en",
                                        "es",
                                        "fr",
                                        "de",
                                        "it",
                                        "pt",
                                        "zh",
                                        "ja",
                                        "ko",
                                        "ru",
                                        "ar",
                                        "hi",
                                    ],
                                    value="Auto",
                                    label="Language",
                                )
                                whisper_format = gr.Dropdown(
                                    ["json", "verbose_json", "text", "srt", "vtt"],
                                    value="json",
                                    label="Response Format",
                                )
                                whisper_temperature = gr.Slider(
                                    0.0, 1.0, value=0.0, step=0.1, label="Temperature"
                                )
                                whisper_transcribe_btn = gr.Button(
                                    "Transcribe", variant="primary"
                                )
                            with gr.Column():
                                whisper_text = gr.Textbox(
                                    label="Text Output", lines=10, interactive=False
                                )
                                whisper_json = gr.JSON(label="JSON Output")

                        async def transcribe_audio(
                            audio: str, lang: str, fmt: str, temp: float
                        ) -> Tuple[str, Dict[str, Any]]:
                            if not audio:
                                return "No audio uploaded", {}
                            lang_code = None if lang == "Auto" else lang
                            result = await whisper_client.transcribe(audio, lang_code, fmt, temp)
                            if fmt in {"text", "srt", "vtt"}:
                                return result.get("text", ""), {}
                            return result.get("text", ""), result

                        whisper_transcribe_btn.click(
                            fn=transcribe_audio,
                            inputs=[
                                whisper_audio,
                                whisper_language,
                                whisper_format,
                                whisper_temperature,
                            ],
                            outputs=[whisper_text, whisper_json],
                        )

                    with gr.TabItem("Info"):
                        with gr.Row():
                            whisper_health_btn = gr.Button("Health")
                            whisper_ready_btn = gr.Button("Ready")
                            whisper_models_btn = gr.Button("Models")
                        whisper_info = gr.JSON(label="Info")

                        async def whisper_health_info() -> Dict[str, Any]:
                            return await whisper_client.health()

                        async def whisper_ready_info() -> Dict[str, Any]:
                            return await whisper_client.readiness()

                        async def whisper_models_info() -> Dict[str, Any]:
                            return await whisper_client.list_models()

                        whisper_health_btn.click(fn=whisper_health_info, outputs=[whisper_info])
                        whisper_ready_btn.click(fn=whisper_ready_info, outputs=[whisper_info])
                        whisper_models_btn.click(fn=whisper_models_info, outputs=[whisper_info])

            with gr.TabItem("OCR"):
                gr.Markdown("### Text Detection and Recognition")
                with gr.Tabs():
                    with gr.TabItem("Extract"):
                        with gr.Row():
                            with gr.Column():
                                ocr_image = gr.Image(label="Upload Image", type="filepath")
                                ocr_language = gr.Dropdown(
                                    ["en", "zh"], value="en", label="Language"
                                )
                                ocr_extract_btn = gr.Button(
                                    "Extract Text", variant="primary"
                                )
                            with gr.Column():
                                ocr_text = gr.Textbox(
                                    label="Extracted Text", lines=8, interactive=False
                                )
                                ocr_result = gr.JSON(label="Details")
                                ocr_timing = gr.Textbox(
                                    label="Performance", interactive=False
                                )

                        async def extract_text(
                            image: str, lang: str
                        ) -> Tuple[str, Dict[str, Any], str]:
                            if not image:
                                return "", {"error": "No image"}, ""
                            result = await ocr_client.extract_text(image, [lang])
                            timing = (
                                f"Detection: {result.get('performance', {}).get('detection_time_ms', 0):.1f} ms, "
                                f"Recognition: {result.get('performance', {}).get('recognition_time_ms', 0):.1f} ms"
                            )
                            return result.get("text", ""), result, timing

                        ocr_extract_btn.click(
                            fn=extract_text,
                            inputs=[ocr_image, ocr_language],
                            outputs=[ocr_text, ocr_result, ocr_timing],
                        )

                    with gr.TabItem("Info"):
                        with gr.Row():
                            ocr_health_btn = gr.Button("Health")
                            ocr_ready_btn = gr.Button("Ready")
                            ocr_models_btn = gr.Button("Models")
                        ocr_info = gr.JSON(label="Info")

                        async def ocr_health_info() -> Dict[str, Any]:
                            return await ocr_client.health()

                        async def ocr_ready_info() -> Dict[str, Any]:
                            return await ocr_client.readiness()

                        async def ocr_models_info() -> Dict[str, Any]:
                            return await ocr_client.list_models()

                        ocr_health_btn.click(fn=ocr_health_info, outputs=[ocr_info])
                        ocr_ready_btn.click(fn=ocr_ready_info, outputs=[ocr_info])
                        ocr_models_btn.click(fn=ocr_models_info, outputs=[ocr_info])

            with gr.TabItem("Pose"):
                gr.Markdown("### Human Pose Estimation")
                with gr.Tabs():
                    with gr.TabItem("Detect"):
                        with gr.Row():
                            with gr.Column():
                                pose_image = gr.Image(label="Upload Image", type="filepath")
                                pose_conf_thresh = gr.Slider(
                                    0.0,
                                    1.0,
                                    value=0.5,
                                    step=0.05,
                                    label="Confidence Threshold",
                                )
                                pose_iou_thresh = gr.Slider(
                                    0.0, 1.0, value=0.45, step=0.05, label="IoU Threshold"
                                )
                                pose_max_det = gr.Slider(
                                    1, 20, value=10, step=1, label="Max Detections"
                                )
                                pose_kp_thresh = gr.Slider(
                                    0.0,
                                    1.0,
                                    value=0.3,
                                    step=0.05,
                                    label="Keypoint Threshold",
                                )
                                pose_detect_btn = gr.Button(
                                    "Detect Poses", variant="primary"
                                )
                            with gr.Column():
                                pose_result = gr.JSON(label="Poses")
                                pose_timing = gr.Textbox(
                                    label="Inference Time", interactive=False
                                )
                                pose_count = gr.Textbox(
                                    label="People Detected", interactive=False
                                )

                        async def detect_poses(
                            image: str,
                            conf: float,
                            iou: float,
                            max_det: int,
                            kp_thresh: float,
                        ) -> Tuple[Dict[str, Any], str, str]:
                            if not image:
                                return {"error": "No image"}, "", ""
                            result = await pose_client.detect_poses(
                                image, conf, iou, int(max_det), kp_thresh
                            )
                            timing = f"{result.get('inference_time_ms', 0):.1f} ms"
                            count = f"{result.get('count', 0)} people"
                            return result, timing, count

                        pose_detect_btn.click(
                            fn=detect_poses,
                            inputs=[
                                pose_image,
                                pose_conf_thresh,
                                pose_iou_thresh,
                                pose_max_det,
                                pose_kp_thresh,
                            ],
                            outputs=[pose_result, pose_timing, pose_count],
                        )

                    with gr.TabItem("Info"):
                        with gr.Row():
                            pose_health_btn = gr.Button("Health")
                            pose_ready_btn = gr.Button("Ready")
                            pose_models_btn = gr.Button("Models")
                        pose_info = gr.JSON(label="Info")

                        async def pose_health_info() -> Dict[str, Any]:
                            return await pose_client.health()

                        async def pose_ready_info() -> Dict[str, Any]:
                            return await pose_client.readiness()

                        async def pose_models_info() -> Dict[str, Any]:
                            return await pose_client.list_models()

                        pose_health_btn.click(fn=pose_health_info, outputs=[pose_info])
                        pose_ready_btn.click(fn=pose_ready_info, outputs=[pose_info])
                        pose_models_btn.click(fn=pose_models_info, outputs=[pose_info])

            with gr.TabItem("Depth"):
                gr.Markdown("### Monocular Depth Estimation")
                with gr.Tabs():
                    with gr.TabItem("Estimate"):
                        with gr.Row():
                            with gr.Column():
                                depth_image = gr.Image(label="Upload Image", type="filepath")
                                depth_format = gr.Dropdown(
                                    ["numpy", "image", "both"],
                                    value="both",
                                    label="Output Format",
                                )
                                depth_colormap = gr.Dropdown(
                                    ["viridis", "plasma", "magma", "turbo", "jet"],
                                    value="viridis",
                                    label="Colormap",
                                )
                                depth_normalize = gr.Checkbox(
                                    label="Normalize Depth", value=True
                                )
                                depth_estimate_btn = gr.Button(
                                    "Estimate Depth", variant="primary"
                                )
                            with gr.Column():
                                depth_viz = gr.Image(label="Depth Visualization")
                                depth_result = gr.JSON(label="Depth Results")
                                depth_timing = gr.Textbox(
                                    label="Inference Time", interactive=False
                                )

                        async def estimate_depth(
                            image: str, fmt: str, colormap: str, normalize: bool
                        ) -> Tuple[Optional[Image.Image], Dict[str, Any], str]:
                            if not image:
                                return None, {"error": "No image"}, ""
                            result = await depth_client.estimate_depth(
                                image, fmt, normalize, colormap
                            )
                            depth_img = None
                            if isinstance(result, dict) and "depth_image" in result:
                                try:
                                    img_data = base64.b64decode(result["depth_image"])
                                    depth_img = Image.open(io.BytesIO(img_data))
                                except Exception:
                                    depth_img = None
                            timing = f"{result.get('inference_time_ms', 0):.1f} ms"
                            return depth_img, result, timing

                        depth_estimate_btn.click(
                            fn=estimate_depth,
                            inputs=[depth_image, depth_format, depth_colormap, depth_normalize],
                            outputs=[depth_viz, depth_result, depth_timing],
                        )

                    with gr.TabItem("Info"):
                        with gr.Row():
                            depth_health_btn = gr.Button("Health")
                            depth_ready_btn = gr.Button("Ready")
                            depth_info_btn = gr.Button("Info")
                        depth_info = gr.JSON(label="Info")

                        async def depth_health_info() -> Dict[str, Any]:
                            return await depth_client.health()

                        async def depth_ready_info() -> Dict[str, Any]:
                            return await depth_client.readiness()

                        async def depth_service_info() -> Dict[str, Any]:
                            return await depth_client.info()

                        depth_health_btn.click(fn=depth_health_info, outputs=[depth_info])
                        depth_ready_btn.click(fn=depth_ready_info, outputs=[depth_info])
                        depth_info_btn.click(fn=depth_service_info, outputs=[depth_info])



            with gr.TabItem("Piper"):
                gr.Markdown("### Text to Speech")
                with gr.Tabs():
                    with gr.TabItem("OpenAI Speech"):
                        with gr.Row():
                            with gr.Column():
                                piper_text = gr.Textbox(
                                    label="Text to Synthesize", lines=5
                                )
                                piper_voice = gr.Dropdown(
                                    choices=["default"], value="default", label="Voice"
                                )
                                piper_refresh = gr.Button("Refresh Voices", size="sm")
                                piper_format = gr.Dropdown(
                                    ["wav", "pcm"], value="wav", label="Format"
                                )
                                piper_speed = gr.Slider(
                                    0.5, 2.0, value=1.0, step=0.1, label="Speed"
                                )
                                piper_synthesize_btn = gr.Button(
                                    "Synthesize", variant="primary"
                                )
                            with gr.Column():
                                piper_audio = gr.Audio(label="Audio Preview")
                                piper_file = gr.File(label="Download File")
                                piper_status = gr.Textbox(
                                    label="Status", interactive=False
                                )

                        async def refresh_voices() -> gr.Dropdown:
                            result = await piper_client.list_voices()
                            voices = [v.get("id") for v in result.get("voices", [])]
                            if not voices:
                                voices = ["default"]
                            return gr.Dropdown(choices=voices, value=voices[0])

                        async def synthesize_speech(
                            text: str, voice: str, fmt: str, speed: float
                        ) -> Tuple[Optional[str], Optional[str], str]:
                            if not text:
                                return None, None, "No text provided"
                            audio_bytes = await piper_client.synthesize_openai(
                                text, voice=voice, response_format=fmt, speed=speed
                            )
                            suffix = ".wav" if fmt == "wav" else ".pcm"
                            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                                tmp.write(audio_bytes)
                                path = tmp.name
                            preview = path if fmt == "wav" else None
                            return preview, path, f"Synthesized {len(text)} characters"

                        piper_refresh.click(fn=refresh_voices, outputs=[piper_voice])
                        piper_synthesize_btn.click(
                            fn=synthesize_speech,
                            inputs=[piper_text, piper_voice, piper_format, piper_speed],
                            outputs=[piper_audio, piper_file, piper_status],
                        )

                    with gr.TabItem("Simple Synthesize"):
                        with gr.Row():
                            with gr.Column():
                                simple_text = gr.Textbox(label="Text", lines=5)
                                simple_format = gr.Dropdown(
                                    ["wav"], value="wav", label="Format"
                                )
                                simple_btn = gr.Button("Synthesize", variant="primary")
                            with gr.Column():
                                simple_audio = gr.Audio(label="Audio Preview")
                                simple_file = gr.File(label="Download File")
                                simple_status = gr.Textbox(
                                    label="Status", interactive=False
                                )

                        async def synthesize_simple(
                            text: str, fmt: str
                        ) -> Tuple[Optional[str], Optional[str], str]:
                            if not text:
                                return None, None, "No text provided"
                            audio_bytes = await piper_client.synthesize_simple(text, fmt)
                            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
                                tmp.write(audio_bytes)
                                path = tmp.name
                            return path, path, "Synthesis complete"

                        simple_btn.click(
                            fn=synthesize_simple,
                            inputs=[simple_text, simple_format],
                            outputs=[simple_audio, simple_file, simple_status],
                        )

                    with gr.TabItem("Info"):
                        with gr.Row():
                            piper_health_btn = gr.Button("Health")
                            piper_voices_btn = gr.Button("Voices")
                        piper_info = gr.JSON(label="Info")

                        async def piper_health_info() -> Dict[str, Any]:
                            return await piper_client.health()

                        async def piper_voices_info() -> Dict[str, Any]:
                            return await piper_client.list_voices()

                        piper_health_btn.click(fn=piper_health_info, outputs=[piper_info])
                        piper_voices_btn.click(fn=piper_voices_info, outputs=[piper_info])

            with gr.TabItem("Service Control"):
                gr.Markdown("### System Service Management")
                services_status = gr.Dataframe(
                    headers=["Service", "Status"], value=[], interactive=False
                )
                with gr.Row():
                    refresh_services_btn = gr.Button("Refresh Status")
                    start_all_btn = gr.Button("Start All (except Ollama)")
                    stop_all_btn = gr.Button("Stop All")

                with gr.Row():
                    service_select = gr.Dropdown(
                        choices=service_mgr.SERVICE_NAMES, label="Service"
                    )
                    start_btn = gr.Button("Start")
                    stop_btn = gr.Button("Stop")
                    restart_btn = gr.Button("Restart")

                service_action_result = gr.Textbox(label="Action Result", interactive=False)

                async def refresh_services() -> List[List[str]]:
                    status = await service_mgr.get_status()
                    return [[name, stat] for name, stat in status.items()]

                async def start_all() -> str:
                    for service in service_mgr.SERVICE_NAMES:
                        if service in {"hailo-ollama", "hailo-device-manager"}:
                            continue
                        await service_mgr.start_service(service)
                    return "Start requested for all services (excluding ollama)."

                async def stop_all() -> str:
                    for service in service_mgr.SERVICE_NAMES:
                        if service == "hailo-device-manager":
                            continue
                        await service_mgr.stop_service(service)
                    return "Stop requested for all services."

                async def start_service(name: str) -> str:
                    if not name:
                        return "Select a service."
                    result = await service_mgr.start_service(name)
                    return result.get("message", result.get("status", "ok"))

                async def stop_service(name: str) -> str:
                    if not name:
                        return "Select a service."
                    result = await service_mgr.stop_service(name)
                    return result.get("message", result.get("status", "ok"))

                async def restart_service(name: str) -> str:
                    if not name:
                        return "Select a service."
                    result = await service_mgr.restart_service(name)
                    return result.get("message", result.get("status", "ok"))

                refresh_services_btn.click(fn=refresh_services, outputs=[services_status])
                start_all_btn.click(fn=start_all, outputs=[service_action_result])
                stop_all_btn.click(fn=stop_all, outputs=[service_action_result])
                start_btn.click(fn=start_service, inputs=[service_select], outputs=[service_action_result])
                stop_btn.click(fn=stop_service, inputs=[service_select], outputs=[service_action_result])
                restart_btn.click(
                    fn=restart_service, inputs=[service_select], outputs=[service_action_result]
                )

    return demo


gradio_demo = build_gradio_interface()
app = gr.mount_gradio_app(app, gradio_demo, path="/")


@app.on_event("startup")
async def startup_event() -> None:
    await monitor.start()


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await monitor.stop()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=7860)
