import bpy
from bpy.app.handlers import persistent
import functools
from . import (
    operators,
    task_queue,
    utils,
)


@persistent
def load_post_handler(context):
    """Handle new blender file load (and new scene load)"""
    if not context:
        context = bpy.context

    # if AI Render has been enabled in this file, do the enable steps
    # right now, to ensure everything is running and in place
    if context.scene.air_props.is_enabled:
        operators.enable_air(context.scene)


@persistent
def render_init_handler(scene):
    """Handle an entire render process about to start"""

    # if AI Render wasn't installed correctly, quit here
    if not utils.is_installation_valid():
        return

    # otherwise, simply track that a render is in progress
    scene.air_props.is_rendering = True
    scene.air_props.animation_init_frame = scene.frame_current


@persistent
def render_pre_handler(scene):
    """Handle a frame render about to start"""

    # if AI Render wasn't installed correctly or isn't enabled, quit here. (Also quit
    # here if we're rendering an animation, because we'll handle that separately).
    if (
        not utils.is_installation_valid()
        or not scene.air_props.is_enabled
        or scene.air_props.is_rendering_animation
        or scene.air_props.is_rendering_animation_manually
    ):
        return

    # otherwise, do the pre-render setup
    # NOTE: We want to do this even if auto_run is disabled, because we need to mute
    # the node group in that case, so that the actual render can be viewed
    operators.do_pre_render_setup(scene)


@persistent
def frame_change_pre_handler(scene):
    """Handle frame change"""

    # if AI Render wasn't installed correctly, quit here
    if not utils.is_installation_valid():
        return

    # if we are rendering, track that we are rendering an animation
    if scene.air_props.is_rendering and int(scene.air_props.animation_init_frame) != int(scene.frame_current):
        scene.air_props.is_rendering_animation = True


@persistent
def render_complete_handler(scene):
    """Handle render completed (this is where the API and Stable Diffusion start)"""

    # if AI Render wasn't installed correctly, or it isn't enabled, or we don't want
    # to run automatically, or we don't have an API Key (and we're not running locally),
    # quit here. (Also quit here if we're rendering an animation, because we'll handle that
    # separately).
    if (
        not utils.is_installation_valid()
        or not scene.air_props.is_enabled
        or not scene.air_props.auto_run
        or scene.air_props.is_rendering_animation
        or scene.air_props.is_rendering_animation_manually
        or (not utils.get_api_key() and not utils.do_use_local_sd())
    ):
        # track that we're not rendering
        scene.air_props.is_rendering = False
        scene.air_props.is_rendering_animation = False

        # then quit
        return

    # check to see if we have a render result
    is_img_ready = bpy.data.images['Render Result'].has_data

    # if it's ready, post to the api
    if is_img_ready:

        # do pre-api setup
        operators.do_pre_api_setup(scene)

        # post to the api (on a different thread, outside the handler)
        task_queue.add(functools.partial(operators.send_to_api, scene))
    else:
        operators.handle_error("Rendered image is not ready. Try generating a new image manually under AI Render > Operation")

    # track that we're no longer rendering
    scene.air_props.is_rendering = False
    scene.air_props.is_rendering_animation = False


def register():
    bpy.app.handlers.load_post.append(load_post_handler)
    bpy.app.handlers.render_init.append(render_init_handler)
    bpy.app.handlers.render_pre.append(render_pre_handler)
    bpy.app.handlers.frame_change_pre.append(frame_change_pre_handler)
    bpy.app.handlers.render_complete.append(render_complete_handler)


def unregister():
    bpy.app.handlers.load_post.remove(load_post_handler)
    bpy.app.handlers.render_init.remove(render_init_handler)
    bpy.app.handlers.render_pre.remove(render_pre_handler)
    bpy.app.handlers.frame_change_pre.remove(frame_change_pre_handler)
    bpy.app.handlers.render_complete.remove(render_complete_handler)
