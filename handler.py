import runpod
import json
import base64
import time
import urllib.request
import urllib.parse
import urllib.error
import uuid
import os
import random
import logging
import websocket

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration
SERVER_ADDRESS = os.getenv('SERVER_ADDRESS', '127.0.0.1')
COMFY_API_URL = f"http://{SERVER_ADDRESS}:8188"
COMFY_INPUT_DIR = "/ComfyUI/input"
WORKFLOW_PATH = "/workflow_api.json"

# Multi-Angle specific configuration
KSAMPLER_NODES = ["116", "126", "136", "146", "156", "166", "176", "186"]
SCALE_NODES = ["112", "122", "132", "142", "152", "162", "172", "182"]
ANGLE_NODES = {
    "118": "close_up",
    "128": "wide_shot",
    "138": "45_right",
    "148": "90_right",
    "158": "aerial_view",
    "168": "low_angle",
    "178": "45_left",
    "188": "90_left",
}
ALL_ANGLES = ["close_up", "wide_shot", "45_right", "90_right", "aerial_view", "low_angle", "45_left", "90_left"]


def queue_prompt(prompt, client_id=None):
    """Submit a workflow to ComfyUI via HTTP POST."""
    payload = {"prompt": prompt}
    if client_id:
        payload["client_id"] = client_id
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(f"{COMFY_API_URL}/prompt", data=data, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        error_body = ""
        try:
            error_body = e.read().decode('utf-8')
        except Exception:
            pass
        logger.error(f"Failed to queue prompt: HTTP {e.code} - {error_body}")
        raise RuntimeError(f"ComfyUI rejected workflow (HTTP {e.code}): {error_body[:500]}")
    except urllib.error.URLError as e:
        logger.error(f"Failed to queue prompt: {e}")
        raise


def get_history(prompt_id):
    """Retrieve workflow execution history from ComfyUI."""
    req = urllib.request.Request(f"{COMFY_API_URL}/history/{prompt_id}")
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.URLError as e:
        logger.error(f"Failed to get history: {e}")
        raise


def get_images(ws, prompt):
    """Wait for workflow completion via WebSocket and retrieve output images."""
    prompt_id = prompt['prompt_id']
    logger.info(f"Waiting for prompt completion: {prompt_id}")

    output_images = {}

    while True:
        try:
            out = ws.recv()
            if isinstance(out, str):
                message = json.loads(out)
                if message['type'] == 'executing':
                    data = message['data']
                    if data['node'] is None and data['prompt_id'] == prompt_id:
                        logger.info("Execution complete")
                        break
            else:
                continue
        except Exception as e:
            logger.error(f"WebSocket receive error: {e}")
            raise

    # Get images from history
    history = get_history(prompt_id)[prompt_id]

    if 'status' in history and history['status'].get('status_str') == 'error':
        error_msgs = history['status'].get('messages', [])
        raise RuntimeError(f"ComfyUI workflow failed: {error_msgs}")

    outputs = history.get('outputs', {})

    for node_id, node_output in outputs.items():
        if 'images' in node_output:
            images_output = []
            for image in node_output['images']:
                # Build URL parameters for image retrieval
                params = {
                    'filename': image['filename'],
                    'type': image.get('type', 'output')
                }
                if 'subfolder' in image and image['subfolder']:
                    params['subfolder'] = image['subfolder']

                # Retrieve image via HTTP
                url = f"{COMFY_API_URL}/view?{urllib.parse.urlencode(params)}"
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=30) as response:
                    image_data = response.read()
                    images_output.append(image_data)

            output_images[node_id] = images_output

    return output_images


def load_workflow(path):
    """Load workflow JSON from file."""
    with open(path, 'r') as f:
        return json.load(f)


def download_file(url, output_path):
    """Download file from URL using urllib."""
    logger.info(f"Downloading from {url}")
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            with open(output_path, 'wb') as out_file:
                out_file.write(response.read())
        logger.info(f"Downloaded to {output_path}")
    except urllib.error.URLError as e:
        logger.error(f"Download failed: {e}")
        raise


def save_base64_to_file(base64_data, temp_dir, filename):
    """Save base64 encoded data to file."""
    # Remove data URL prefix if present
    if ',' in base64_data:
        base64_data = base64_data.split(',', 1)[1]

    image_bytes = base64.b64decode(base64_data)

    # Detect format
    if image_bytes.startswith(b'\x89PNG'):
        ext = '.png'
    elif image_bytes.startswith(b'\xff\xd8\xff'):
        ext = '.jpg'
    else:
        ext = '.png'  # default

    file_path = os.path.join(temp_dir, f"{filename}{ext}")
    with open(file_path, 'wb') as f:
        f.write(image_bytes)

    logger.info(f"Saved base64 data to {file_path}")
    return file_path


def process_input(data, temp_dir, filename, input_type="image"):
    """Process input from various formats: URL, base64, or file path."""
    if not data:
        return None

    # Check if it's a URL
    if isinstance(data, str) and (data.startswith('http://') or data.startswith('https://')):
        output_path = os.path.join(temp_dir, filename)
        download_file(data, output_path)
        return output_path

    # Check if it's base64
    elif isinstance(data, str) and (data.startswith('data:') or len(data) > 100):
        return save_base64_to_file(data, temp_dir, filename)

    # Check if it's a file path
    elif isinstance(data, str) and os.path.exists(data):
        logger.info(f"Using existing file: {data}")
        return data

    return None


def get_image_input(job_input, task_id):
    """Extract image from various input formats."""
    # Check direct keys
    if 'image_url' in job_input:
        return process_input(job_input['image_url'], COMFY_INPUT_DIR, f"{task_id}_input")
    elif 'image_base64' in job_input:
        # Directly save base64 - no need for format detection heuristic
        return save_base64_to_file(job_input['image_base64'], COMFY_INPUT_DIR, f"{task_id}_input")
    elif 'image_path' in job_input:
        return process_input(job_input['image_path'], COMFY_INPUT_DIR, f"{task_id}_input")
    elif 'image' in job_input:
        return process_input(job_input['image'], COMFY_INPUT_DIR, f"{task_id}_input")

    # Check nested images object
    elif 'images' in job_input and isinstance(job_input['images'], dict):
        if 'reference_image' in job_input['images']:
            return process_input(job_input['images']['reference_image'], COMFY_INPUT_DIR, f"{task_id}_input")

    return None


def wait_for_comfyui_http(timeout=180):
    """Wait for ComfyUI HTTP endpoint to be ready."""
    logger.info(f"Waiting for ComfyUI at {COMFY_API_URL}...")
    start_time = time.time()
    attempts = 0
    max_attempts = timeout

    while attempts < max_attempts:
        try:
            req = urllib.request.Request(f"{COMFY_API_URL}/system_stats")
            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status == 200:
                    logger.info("ComfyUI HTTP is ready!")
                    return True
        except (urllib.error.URLError, urllib.error.HTTPError):
            pass

        attempts += 1
        time.sleep(1)

        if attempts % 30 == 0:
            logger.info(f"Still waiting for ComfyUI... ({attempts}/{max_attempts})")

    raise TimeoutError(f"ComfyUI did not become ready within {timeout} seconds")


def connect_websocket_with_retry(max_attempts=36, retry_delay=5):
    """Connect to ComfyUI WebSocket with retry logic. Returns (ws, client_id)."""
    client_id = str(uuid.uuid4())
    ws_url = f"ws://{SERVER_ADDRESS}:8188/ws?clientId={client_id}"

    for attempt in range(max_attempts):
        try:
            logger.info(f"Attempting WebSocket connection (attempt {attempt + 1}/{max_attempts})")
            ws = websocket.create_connection(ws_url, timeout=600)
            logger.info(f"WebSocket connected successfully (clientId={client_id})")
            return ws, client_id
        except Exception as e:
            logger.warning(f"WebSocket connection failed: {e}")
            if attempt < max_attempts - 1:
                time.sleep(retry_delay)
            else:
                raise RuntimeError(f"Failed to connect to WebSocket after {max_attempts} attempts")


def handler(job):
    """Main handler for Qwen Image Edit Multi-Angle workflow."""
    task_id = str(uuid.uuid4())
    input_file_path = None
    ws = None

    try:
        job_input = job.get("input", {})

        # Extract parameters (NO prompt parameter)
        seed = job_input.get("seed", 0)
        megapixels = job_input.get("megapixels", 1.0)

        logger.info(f"Task {task_id}: Processing multi-angle image edit")
        logger.info(f"Parameters - megapixels: {megapixels}")

        # Handle seed - generate 8 independent seeds if seed is 0 or -1
        if seed == 0 or seed == -1:
            seeds = {angle: random.randint(0, 2**53) for angle in ALL_ANGLES}
            logger.info(f"Generated independent seeds for each angle")
        else:
            seeds = {angle: seed for angle in ALL_ANGLES}
            logger.info(f"Using seed: {seed} for all angles")

        # Get image input
        os.makedirs(COMFY_INPUT_DIR, exist_ok=True)
        input_file_path = get_image_input(job_input, task_id)

        if not input_file_path:
            return {"error": "Missing required parameter: image (provide image_url, image_base64, image_path, or images.reference_image)"}

        # Get filename for ComfyUI
        input_filename = os.path.basename(input_file_path)
        logger.info(f"Input image: {input_filename}")

        # Load workflow
        workflow = load_workflow(WORKFLOW_PATH)

        # Inject image into LoadImage node (node "200", NOT "76")
        workflow["200"]["inputs"]["image"] = input_filename

        # Inject megapixels into all 8 ImageScaleToTotalPixels nodes
        for node_id in SCALE_NODES:
            workflow[node_id]["inputs"]["megapixels"] = megapixels

        # Inject seeds into all 8 KSampler nodes
        seed_mapping = {
            "116": seeds["close_up"],
            "126": seeds["wide_shot"],
            "136": seeds["45_right"],
            "146": seeds["90_right"],
            "156": seeds["aerial_view"],
            "166": seeds["low_angle"],
            "176": seeds["45_left"],
            "186": seeds["90_left"],
        }
        for node_id, seed_val in seed_mapping.items():
            workflow[node_id]["inputs"]["seed"] = seed_val

        # Wait for ComfyUI HTTP endpoint
        wait_for_comfyui_http(timeout=180)

        # Connect WebSocket
        ws, client_id = connect_websocket_with_retry(max_attempts=36, retry_delay=5)

        # Queue workflow
        logger.info("Submitting workflow to ComfyUI...")
        prompt_response = queue_prompt(workflow, client_id=client_id)
        prompt_id = prompt_response.get('prompt_id')

        if not prompt_id:
            return {"error": "Failed to get prompt_id from ComfyUI"}

        logger.info(f"Workflow queued with prompt_id: {prompt_id}")

        # Wait for completion and get images
        output_images = get_images(ws, {'prompt_id': prompt_id})

        # Close WebSocket
        ws.close()
        ws = None

        # Collect outputs from 8 SaveImage nodes with partial failure tolerance
        result_images = {}
        missing_angles = []

        for node_id, angle_name in ANGLE_NODES.items():
            if node_id in output_images and output_images[node_id]:
                image_data = output_images[node_id][0]
                result_images[angle_name] = base64.b64encode(image_data).decode('utf-8')
            else:
                missing_angles.append(angle_name)
                logger.warning(f"Missing output for angle: {angle_name} (node {node_id})")

        # If ALL 8 angles failed, return error
        if len(result_images) == 0:
            return {"error": "All 8 angles failed to generate"}

        # Build successful angles list
        successful_angles = list(result_images.keys())

        logger.info(f"Task {task_id}: Complete - {len(successful_angles)}/8 angles generated")
        if missing_angles:
            logger.warning(f"Missing angles: {missing_angles}")

        # Return response with all successful images
        response = {
            "images": result_images,
            "angles": successful_angles,
            "missing_angles": missing_angles,
            "seed": seeds if seed == 0 or seed == -1 else seed,
            "prompt_id": prompt_id
        }

        return response

    except Exception as e:
        logger.error(f"Task {task_id} failed: {str(e)}", exc_info=True)
        return {"error": f"Processing failed: {str(e)}"}

    finally:
        # Cleanup
        if ws:
            try:
                ws.close()
            except Exception:
                pass

        if input_file_path and os.path.exists(input_file_path):
            try:
                os.remove(input_file_path)
                logger.info(f"Cleaned up input file: {input_file_path}")
            except Exception as e:
                logger.warning(f"Failed to cleanup input file: {e}")


if __name__ == "__main__":
    wait_for_comfyui_http()
    runpod.serverless.start({"handler": handler})
