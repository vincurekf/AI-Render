import os
import bpy
import base64
import requests
import json
from .. import (
    config,
    operators,
    utils,
)
from colorama import Fore


# CORE FUNCTIONS:

def load_workflow(context, workflow_file):
    workflow_path = os.path.join(get_workflows_path(context), workflow_file)
    with open(workflow_path, 'r') as file:
        return json.load(file)


def get_active_workflow(context):
    return context.scene.air_props.comfyui_workflows


def upload_image(img_file):

    # Get the image path from _io.BufferedReader
    image_path = img_file.name
    print("\nLOG IMAGE PATH:")
    print(image_path)

    # Post the image to the /upload/image endpoint
    server_url = get_server_url("/upload/image")
    print(Fore.WHITE + "\nSENDING REQUEST TO: " + server_url)

    # prepare the data
    headers = create_headers()
    data = {"subfolder": "test", "type": "input"}
    files = {'image': (os.path.basename(image_path), open(image_path, 'rb'))}
    resp = requests.post(server_url, files=files, data=data, headers=headers)

    print("\nLOG UPLOAD IMAGE RESPONSE:")
    # b'{"name": "ai-render-1712271170-cat-1-before-y939nzr0.png", "subfolder": "", "type": "input"}'
    print(resp.content)

    # add a base 64 encoded image to the params
    # params["init_images"] = ["data:image/png;base64," + base64.b64encode(img_file.read()).decode()]
    # img_file.close()

    return resp.json()["subfolder"], resp.json()["name"]


def generate(params, img_file, filename_prefix, props):

    # Load the workflow
    workflow = load_workflow(bpy.context, get_active_workflow(bpy.context))
    print(f"{Fore.LIGHTWHITE_EX}\nLOG WORKFLOW: {Fore.RESET}{get_active_workflow(bpy.context)}")
    # pprint(workflow)

    params["denoising_strength"] = round(1 - params["image_similarity"], 4)
    params["sampler_index"] = params["sampler"]

    # upload the image, get the subfolder and image name
    subfolder, img_name = upload_image(img_file)

    # Add the image path to the params
    params["init_images"] = [f"{subfolder}/{img_name}"]

    # map the params to the ComfyUI nodes
    json_obj = map_params(params, workflow)
    data = {"prompt": json_obj}

    # prepare the server url
    try:
        server_url = get_server_url("/prompt")
    except:
        return operators.handle_error(f"You need to specify a location for the local Stable Diffusion server in the add-on preferences. [Get help]({config.HELP_WITH_LOCAL_INSTALLATION_URL})", "local_server_url_missing")

    # send the API request
    response = do_post(url=server_url, data=data)

    if response == False:
        return False

    # handle the response
    if response.status_code == 200:
        return handle_success(response, filename_prefix)
    else:
        return handle_error(response)


def upscale(img_file, filename_prefix, props):

    # prepare the params
    data = {
        "resize_mode": 0,
        "show_extras_results": True,
        "gfpgan_visibility": 0,
        "codeformer_visibility": 0,
        "codeformer_weight": 0,
        "upscaling_resize": props.upscale_factor,
        "upscaling_resize_w": utils.sanitized_upscaled_width(max_upscaled_image_size()),
        "upscaling_resize_h": utils.sanitized_upscaled_height(max_upscaled_image_size()),
        "upscaling_crop": True,
        "upscaler_1": props.upscaler_model,
        "upscaler_2": "None",
        "extras_upscaler_2_visibility": 0,
        "upscale_first": True,
    }

    # add a base 64 encoded image to the params
    data["image"] = "data:image/png;base64," + \
        base64.b64encode(img_file.read()).decode()
    img_file.close()

    # prepare the server url
    try:
        server_url = get_server_url("/sdapi/v1/extra-single-image")
    except:
        return operators.handle_error(f"You need to specify a location for the local Stable Diffusion server in the add-on preferences. [Get help]({config.HELP_WITH_LOCAL_INSTALLATION_URL})", "local_server_url_missing")

    # send the API request
    response = do_post(server_url, data)

    # print log info for debugging
    print("DEBUG COMFY")
    debug_log(response)

    if response == False:
        return False

    # handle the response
    if response.status_code == 200:
        return handle_success(response, filename_prefix)
    else:
        return handle_error(response)


def handle_success(response, filename_prefix):

    # ensure we have the type of response we are expecting
    try:
        response_obj = response.json()
        # base64_img = response_obj.get("images", [False])[0] or response_obj.get("image")
    except:
        print("Automatic1111 response content: ")
        print(response.content)
        return operators.handle_error("Received an unexpected response from the Automatic1111 Stable Diffusion server.", "unexpected_response")

    # create a temp file
    try:
        output_file = utils.create_temp_file(filename_prefix + "-")
    except:
        return operators.handle_error("Couldn't create a temp file to save image.", "temp_file")

    # decode base64 image
    try:
        pass
        # img_binary = base64.b64decode(base64_img.replace("data:image/png;base64,", ""))
    except:
        return operators.handle_error("Couldn't decode base64 image from the ComfyUI Stable Diffusion server.", "base64_decode")

    # save the image to the temp file
    try:
        with open(output_file, 'wb') as file:
            pass
            # file.write(img_binary)

    except:
        return operators.handle_error("Couldn't write to temp file.", "temp_file_write")

    # return the temp file
    return output_file


def handle_error(response):
    if response.status_code == 404:

        try:
            response_obj = response.json()
            if response_obj.get('detail') and response_obj['detail'] == "Not Found":
                return operators.handle_error(f"It looks like the Automatic1111 server is running, but it's not in API mode. [Get help]({config.HELP_WITH_AUTOMATIC1111_NOT_IN_API_MODE_URL})", "automatic1111_not_in_api_mode")
            elif response_obj.get('detail') and response_obj['detail'] == "Sampler not found":
                return operators.handle_error("The sampler you selected is not available on the Automatic1111 Stable Diffusion server. Please select a different sampler.", "invalid_sampler")
            else:
                return operators.handle_error(f"An error occurred in the ComfyUI server. Full server response: {json.dumps(response_obj)}", "unknown_error")
        except:
            return operators.handle_error(f"It looks like the Automatic1111 server is running, but it's not in API mode. [Get help]({config.HELP_WITH_AUTOMATIC1111_NOT_IN_API_MODE_URL})", "automatic1111_not_in_api_mode")

    else:
        print(Fore.GREEN + "ERROR DETAILS: " + Fore.RESET)
        print(json.dumps(response.json(), indent=2))
        return operators.handle_error(f"AN ERROR occurred in the ComfyUI server.", "unknown_error_response")


# PRIVATE SUPPORT FUNCTIONS:

def print_with_colors(json_dict):
    def find_prompts(data, class_type='KSampler'):
        for key, value in data.items():
            if isinstance(value, dict):
                if value.get('class_type') == class_type:
                    return value['inputs'].get('positive', [''])[0], value['inputs'].get('negative', [''])[0]
                positive_key, negative_key = find_prompts(value, class_type)
                if positive_key or negative_key:
                    return positive_key, negative_key
        return None, None

    def recursive_print(data, positive_key=None, negative_key=None, path=""):
        for key, value in data.items():
            # Maintain the path traveled in the JSON structure
            json_traverse_path = f"{path}/{key}"
            if isinstance(value, dict):
                recursive_print(value, positive_key,
                                negative_key, json_traverse_path)
            elif isinstance(value, list) and all(isinstance(item, dict) for item in value):
                for item in value:
                    recursive_print(item, positive_key,
                                    negative_key, json_traverse_path)
            else:
                if key == 'prompt' or (key == 'text' and positive_key and positive_key in json_traverse_path):
                    print(
                        Fore.GREEN + f"{key}: {Fore.LIGHTGREEN_EX}{value}" + Fore.RESET)
                elif key == 'negative_prompt' or (key == 'text' and negative_key and negative_key in json_traverse_path):
                    print(
                        Fore.RED + f"{key}: {Fore.LIGHTRED_EX}{value}" + Fore.RESET)
                elif key in ['sampler', 'scheduler', 'denoising_strength', 'steps', 'seed', 'cfg_scale', 'denoise', 'sampler_name', 'cfg']:
                    print(
                        Fore.MAGENTA + f"{key}: {Fore.LIGHTMAGENTA_EX}{value}" + Fore.RESET)
                elif key in ['init_images', 'image']:
                    print(
                        Fore.YELLOW + f"{key}: {Fore.LIGHTYELLOW_EX}{value}" + Fore.RESET)

    positive_node, negative_node = find_prompts(json_dict)
    recursive_print(json_dict, positive_node, negative_node)


def create_headers():
    return {
        "User-Agent": f"Blender/{bpy.app.version_string}",
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate, br",
    }


def get_server_url(path):
    base_url = utils.local_sd_url().rstrip("/").strip()
    if not base_url:
        raise Exception("Couldn't get the Automatic1111 server url")
    else:
        return base_url + path


def map_KSampler(params, json_obj):

    KSampler = None

    for key, value in json_obj.items():
        if value['class_type'] == 'KSampler':
            KSampler = key

            value['inputs']['seed'] = params['seed']
            value['inputs']['steps'] = params['steps']
            value['inputs']['cfg'] = params['cfg_scale']
            value['inputs']['sampler_name'] = params['sampler']
            value['inputs']['scheduler'] = params['scheduler']
            value['inputs']['denoise'] = params['denoising_strength']

    return json_obj, KSampler


def map_prompts(params, json_obj):

    positive = None
    negative = None

    # Get the node number of the positive and negative prompta
    for key, value in json_obj.items():
        if value['class_type'] == 'KSampler':
            positive = value['inputs']['positive'][0]
            negative = value['inputs']['negative'][0]

    for key, value in json_obj.items():
        if value['class_type'] == 'CLIPTextEncode':
            if key == positive:
                value['inputs']['text'] = params['prompt']
            if key == negative:
                value['inputs']['text'] = params['negative_prompt']

    return json_obj, positive, negative


def map_init_image(params, json_obj):

    connected_image = None

    # Get the node number of the VAEEncode
    for key, value in json_obj.items():
        if value['class_type'] == 'VAEEncode':
            connected_image = value['inputs']['pixels'][0]

    for key, value in json_obj.items():
        if value['class_type'] == 'LoadImage':
            if key == connected_image:  # If the LoadImage is connected to the VAEEncode
                value['inputs']['image'] = params['init_images'][0]

    return json_obj, connected_image


def map_params(params, json_obj):

    print("\nLOG PARAMS:")
    print_with_colors(params)

    # Map the params to the ComfyUI nodes
    json_obj, KSampler = map_KSampler(params, json_obj)
    json_obj, positive, negative = map_prompts(params, json_obj)
    json_obj, connected_image = map_init_image(params, json_obj)

    # print("\nMAPPING COMFYUI NODES:")
    # print(Fore.MAGENTA + "KSAMPLER: " + Fore.RESET + KSampler)
    # print(Fore.GREEN + "POSITIVE PROMPT: " + Fore.RESET + positive)
    # print(Fore.RED + "NEGATIVE PROMPT: " + Fore.RESET + negative)
    # print(Fore.YELLOW + "IMAGE CONNECTED TO VAE ENCODER: " + Fore.RESET + connected_image)

    # Save mapped json to local file
    with open('sd_backends/comfyui/_mapped.json', 'w') as f:
        json.dump(json_obj, f, indent=4)

    return json_obj


def do_post(url, data):

    # send the API request
    print(Fore.WHITE + "\nSENDING REQUEST TO: " + url)
    print("\nLOG REQUEST DATA:")
    print_with_colors(data)

    try:
        return requests.post(url, json=data, headers=create_headers(), timeout=utils.local_sd_timeout())
    except requests.exceptions.ConnectionError:
        return operators.handle_error(f"The local Stable Diffusion server couldn't be found. It's either not running, or it's running at a different location than what you specified in the add-on preferences. [Get help]({config.HELP_WITH_LOCAL_INSTALLATION_URL})", "local_server_not_found")
    except requests.exceptions.MissingSchema:
        return operators.handle_error(f"The url for your local Stable Diffusion server is invalid. Please set it correctly in the add-on preferences. [Get help]({config.HELP_WITH_LOCAL_INSTALLATION_URL})", "local_server_url_invalid")
    except requests.exceptions.ReadTimeout:
        return operators.handle_error("The local Stable Diffusion server timed out. Set a longer timeout in AI Render preferences, or use a smaller image size.", "timeout")


def debug_log(response):
    print("request body:")
    print(response.request.body)
    print("\n")

    print("response body:")
    # print(response.content)

    try:
        print(response.json())
    except:
        print("body not json")


# PUBLIC SUPPORT FUNCTIONS:

def get_workflows_path(context):
    return utils.get_addon_preferences().workflows_path


def get_workflows():
    workflows_path = get_workflows_path(bpy.context)
    workflow_files = [f for f in os.listdir(workflows_path) if os.path.isfile(
        os.path.join(workflows_path, f)) and f.endswith(".json")]
    workflow_tuples = [(f, f, "", i) for i, f in enumerate(workflow_files)]

    return workflow_tuples


def get_samplers():
    # NOTE: Keep the number values (fourth item in the tuples) in sync with DreamStudio's
    # values (in stability_api.py). These act like an internal unique ID for Blender
    # to use when switching between the lists.
    return [
        ('euler', 'euler', '', 10),
        ('euler_ancestral', 'euler_ancestral', '', 20),
        ('heun', 'heun', '', 30),
        ('heunpp2', 'heunpp2', '', 40),
        ('dpm_2', 'dpm_2', '', 50),
        ('dpm_2_ancestral', 'dpm_2_ancestral', '', 60),
        ('lms', 'lms', '', 70),
        ('dpm_fast', 'dpm_fast', '', 80),
        ('dpm_adaptive', 'dpm_adaptive', '', 90),
        ('dpmpp_2s_ancestral', 'dpmpp_2s_ancestral', '', 100),
        ('dpmpp_sde', 'dpmpp_sde', '', 110),
        ('dpmpp_sde_gpu', 'dpmpp_sde_gpu', '', 120),
        ('dpmpp_2m', 'dpmpp_2m', '', 130),
        ('dpmpp_2m_sde', 'dpmpp_2m_sde', '', 140),
        ('dpmpp_2m_sde_gpu', 'dpmpp_2m_sde_gpu', '', 150),
        ('dpmpp_3m_sde', 'dpmpp_3m_sde', '', 160),
        ('ddpm', 'ddpm', '', 170),
        ('lcm', 'lcm', '', 180),
        ('ddim', 'ddim', '', 190),
        ('uni_pc', 'uni_pc', '', 200),
        ('uni_pc_bh2', 'uni_pc_bh2', '', 210)
    ]


def get_schedulers():
    return [
        ('normal', 'normal', '', 10),
        ('karras', 'karras', '', 20),
        ('exponential', 'exponential', '', 30),
        ('sgm_uniform', 'sgm_uniform', '', 40),
        ('simple', 'simple', '', 50),
        ('ddim_uniform', 'ddim_uniform', '', 60),
    ]


def default_sampler():
    return 'dpmpp_2m'


def get_upscaler_models(context):
    models = context.scene.air_props.automatic1111_available_upscaler_models

    if (not models):
        return []
    else:
        enum_list = []
        for item in models.split("||||"):
            enum_list.append((item, item, ""))
        return enum_list


def is_upscaler_model_list_loaded(context=None):
    if context is None:
        context = bpy.context
    return context.scene.air_props.automatic1111_available_upscaler_models != ""


def default_upscaler_model():
    return 'ESRGAN_4x'


def get_image_format():
    return 'PNG'


def supports_negative_prompts():
    return True


def supports_choosing_model():
    # TODO - This should be set to true
    # and a get_model() shoulb be used to get the model list from the ComfyUI API
    return False


def supports_upscaling():
    return False


def supports_reloading_upscaler_models():
    return True


def supports_inpainting():
    return False


def supports_outpainting():
    return False


def min_image_size():
    return 128 * 128


def max_image_size():
    return 2048 * 2048


def max_upscaled_image_size():
    return 4096 * 4096


def is_using_sdxl_1024_model(props):
    # TODO: Use the actual model loaded in Automatic1111. For now, we're just
    # returning false, because that way the UI will allow the user to select
    # more image size options.
    return False


def get_available_controlnet_models(context):
    models = context.scene.air_props.controlnet_available_models

    if (not models):
        return []
    else:
        enum_list = []
        for item in models.split("||||"):
            enum_list.append((item, item, ""))
        return enum_list


def get_available_controlnet_modules(context):
    modules = context.scene.air_props.controlnet_available_modules

    if (not modules):
        return []
    else:
        enum_list = []
        for item in modules.split("||||"):
            enum_list.append((item, item, ""))
        return enum_list


def choose_controlnet_defaults(context):
    models = get_available_controlnet_models(context)
    modules = get_available_controlnet_modules(context)

    if (not models) or (not modules):
        return

    # priority order for models and modules
    priority_order = ['depth', 'openpose', 'normal', 'canny', 'scribble']

    # choose a matching model and module in the priority order:
    for item in priority_order:
        model_selection = None
        module_selection = None

        for model in models:
            if item in model[0]:
                model_selection = model[0]
                break

        for module in modules:
            if item in module[0]:
                module_selection = module[0]
                break

        if model_selection and module_selection:
            context.scene.air_props.controlnet_model = model_selection
            context.scene.air_props.controlnet_module = module_selection
            return


def load_upscaler_models(context):
    try:
        # set a flag to indicate whether the list of models has already been loaded
        was_already_loaded = is_upscaler_model_list_loaded(context)

        # get the list of available upscaler models from the Automatic1111 api
        server_url = get_server_url("/sdapi/v1/upscalers")
        headers = {"Accept": "application/json"}
        response = requests.get(server_url, headers=headers, timeout=5)
        response_obj = response.json()
        print("Upscaler models returned from Automatic1111 API:")
        print(response_obj)

        # store the list of models in the scene properties
        if not response_obj:
            return operators.handle_error(f"No upscaler models are installed in Automatic1111. [Get help]({config.HELP_WITH_AUTOMATIC1111_UPSCALING_URL})")
        else:
            # map the response object to a list of model names
            upscaler_models = []
            for model in response_obj:
                if (model["name"] != "None"):
                    upscaler_models.append(model["name"])
            context.scene.air_props.automatic1111_available_upscaler_models = "||||".join(
                upscaler_models)

            # if the list of models was not already loaded, set the default model
            if not was_already_loaded:
                context.scene.air_props.upscaler_model = default_upscaler_model()

            # return success
            return True
    except:
        return operators.handle_error(f"Couldn't get the list of available upscaler models from the Automatic1111 server. [Get help]({config.HELP_WITH_AUTOMATIC1111_UPSCALING_URL})")


def load_controlnet_models(context):
    try:
        # get the list of available controlnet models from the Automatic1111 api
        server_url = get_server_url("/controlnet/model_list")
        headers = {"Accept": "application/json"}
        response = requests.get(server_url, headers=headers, timeout=5)
        response_obj = response.json()
        print("ControlNet models returned from Automatic1111 API:")
        print(response_obj)

        # store the list of models in the scene properties
        models = response_obj["model_list"]
        if not models:
            return operators.handle_error(f"You don't have any ControlNet models installed. You will need to download them from Hugging Face. [Get help]({config.HELP_WITH_CONTROLNET_URL})")
        else:
            context.scene.air_props.controlnet_available_models = "||||".join(
                models)
            return True
    except:
        return operators.handle_error(f"Couldn't get the list of available ControlNet models from the Automatic1111 server. Make sure ControlNet is installed and activated. [Get help]({config.HELP_WITH_CONTROLNET_URL})")


def load_controlnet_modules(context):
    try:
        # get the list of available controlnet modules from the Automatic1111 api
        server_url = get_server_url("/controlnet/module_list")
        headers = {"Accept": "application/json"}
        response = requests.get(server_url, headers=headers, timeout=5)
        response_obj = response.json()
        print("ControlNet modules returned from Automatic1111 API:")
        print(response_obj)

        # sort the modules in alphabetical order, and then store them in the scene
        # properties
        modules = response_obj["module_list"]
        modules.sort()
        context.scene.air_props.controlnet_available_modules = "||||".join(
            modules)
        return True
    except:
        return operators.handle_error(f"Couldn't get the list of available ControlNet modules from the Automatic1111 server. Make sure ControlNet is installed and activated. [Get help]({config.HELP_WITH_CONTROLNET_URL})")
