import atexit
import threading
import time

from scullery import messagebus

from . import ChandlerConsole, core, group_lighting, universes

logger = core.logger
soundLock = threading.Lock()


# Locals for performance... Is this still a thing??
float = float
abs = abs
int = int
max = max
min = min


@core.cl_context.entry_point
def cl_refresh_fixtures(topic, val):
    # Deal with fixtures in this universe that aren't actually attached to this object yet.
    for i in range(5):
        try:
            for i in universes.fixtures:
                f = universes.fixtures[i]()
                if not f:
                    continue
                if f.universe == val or val is None:
                    f.cl_assign(f.universe, f.startAddress)
            break
        except RuntimeError:
            # Should there be some kind of dict changed size problem, retry
            time.sleep(0.1)


messagebus.subscribe("/chandler/command/refreshFixtures", cl_refresh_fixtures)


def pollsounds():
    for b in core.iter_boards():
        for i in b.active_groups:
            i.check_sound_state()


def poll_board_groups(board: ChandlerConsole.ChandlerConsole, t=None):
    "Poll groups in the board"
    t = t or time.time()

    # Remember that groups get rendered in ascending priority order here
    for i in board.active_groups:
        # We don't need to call render() if the frame is a static group and the opacity
        # and all that is the same, we can just re-layer it on top of the values
        if i.poll_again_flag or (
            i.cue.length
            and ((time.time() - i.entered_cue) > i.cuelen * (60 / i.bpm))
        ):
            i.poll_again_flag = False
            i.poll()


lastrendered = 0

run = [True]

frame_wait = threading.Event()


def cl_loop():
    global lastrendered

    # This function is apparently slightly slow?
    u_cache = universes.getUniverses()
    u_cache_time = time.time()
    frame_number = core.started_frame_number
    last = 0

    while run[0]:
        frame_number += 1
        core.started_frame_number = frame_number
        t = time.time()
        core.frame_rate = 1 / (t - last)
        last = t
        try:
            with core.cl_context:
                # Profiler says this needs a cache
                # Todo race condition but i think it's just a flaky test issue
                if (
                    t - u_cache_time > 1
                ) or universes.last_state_update > u_cache_time:
                    u_cache = universes.getUniverses()
                    u_cache_time = t

                do_gui_push = False
                # Only needed when we don't know length in advance
                # so it doesn't need fast response its just a fallback
                if t - lastrendered > 1 / 3:
                    pollsounds()
                    do_gui_push = True
                    lastrendered = t

                for b in core.boards.values():
                    poll_board_groups(b)
                    if do_gui_push:
                        b.cl_gui_push(u_cache)

            changed = {}

            # The pre-render step has to
            # happen before we start compositing on the layers

            # TODO the boards count can change
            with core.cl_context:
                with group_lighting.render_loop_lock:
                    for b in core.boards.values():
                        changed.update(
                            group_lighting.mark_and_reset_changed_universes(
                                b, u_cache
                            )
                        )

                    for b in core.boards.values():
                        c = group_lighting.composite_layers_from_board(
                            b, u=u_cache
                        )
                        changed.update(c)

            group_lighting.do_output(changed, u_cache)

            # Don't go to the next frame until all events and tasks from this frame are done
            # But if the action queue is empty, we skip the step
            queue_wait = False
            if core.action_queue:
                queue_wait = True
                core.serialized_async_with_core_lock(frame_wait.set)

            core.process_next_frame_actions()

            # Sleep happens at the end, ideally the next frame actions could be done before rendering
            # and we could save some latency.
            time.sleep(1 / 60)

            if queue_wait:
                # Don't go to the next frame until all events and tasks from this frame are done
                # Waiting happens after sleep because i think it uses more cpu
                # than just sleeping
                frame_wait.wait(1)
                frame_wait.clear()

            core.completed_frame_number = frame_number

        except Exception:
            logger.exception("Wat")


thread = threading.Thread(target=cl_loop, name="ChandlerThread", daemon=True)
thread.start()


def STOP(*a):
    run[0] = False


atexit.register(STOP)
messagebus.subscribe("/system/shutdown", STOP)
