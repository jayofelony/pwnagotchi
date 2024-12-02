import os
import queue
import glob
import _thread
import threading
import importlib, importlib.util
import logging
import time
import prctl


default_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "default")
loaded = {}
database = {}
locks = {}
exitFlag = 0
plugin_event_queues = {}
plugin_thread_workers = {}

def dummy_callback():
    pass

# callback to run "on_load" in a separate thread for old plugins
# that use on_load like main() and don't return from on_load
# until they are unloading
def run_once(pqueue, event_name, *args, **kwargs):
    try:
        prctl.set_name("R1_%s_%s" % (pqueue.plugin_name, event_name))
        pqueue.process_event(event_name, *args, *kwargs)
        logging.debug("Thread for %s %s exiting" % (pqueue.plugin_name, event_name))
    except Exception as e:
        logging.exception("Thread for %s, %s, %s, %s" % (pqueue.plugin_name, event_name, repr(args), repr(kwargs)))

class PluginEventQueue(threading.Thread):
    def __init__(self, plugin_name):
        try:
            self._worker_thread = threading.Thread.__init__(self, daemon=True)
            self.plugin_name = plugin_name
            self.work_queue = queue.Queue()
            self.queue_lock = threading.Lock()
            self.load_handler = None
            self.keep_going = True
            logging.debug("PLUGIN EVENT QUEUE FOR %s starting %s" % (plugin_name, repr(self.load_handler)))
            self.start()
        except Exception as e:
            logging.exception(e)

    def __del__(self):
        self.keep_going = False
        self._worker_thread.join()
        if self.load_handler:
            self.load_handler.join()

    def AddWork(self, event_name, *args, **kwargs):
        if event_name == "loaded":
            # spawn separate thread, because many plugins use on_load as a "main" loop
            # this way on_load can continue if it needs, while other events get processed
            try:
                cb_name = 'on_%s' % event_name
                callback = getattr(loaded[self.plugin_name], cb_name, None)
                if callback:
                    self.load_handler = threading.Thread(target=run_once,
                                                         args=(self, event_name, *args),
                                                         kwargs=kwargs,
                                                         daemon=True)
                    self.load_handler.start()
                else:
                    self.load_handler = None
            except Exception as e:
                logging.exception(e)
        else:
            self.work_queue.put([event_name, args, kwargs])

    def run(self):
        logging.debug("Worker thread starting for %s"%(self.plugin_name))
        prctl.set_name("PLG %s" % self.plugin_name)
        self.process_events()
        logging.info("Worker thread exiting for %s"%(self.plugin_name))

    def process_event(self, event_name, *args, **kwargs):
        cb_name = 'on_%s' % event_name
        callback = getattr(loaded[self.plugin_name], cb_name, None)
        logging.debug("%s.%s: %s" % (self.plugin_name, event_name, repr(args)))
        if callback:
            callback(*args, **kwargs)

    def process_events(self):
        global exitFlag
        plugin_name = self.plugin_name
        work_queue = self.work_queue

        while not exitFlag and self.keep_going:
            try:
                data = work_queue.get(timeout=2)
                (event_name, args, kwargs) = data
                self.process_event(event_name, *args, **kwargs)
            except queue.Empty as e:
                pass
            except Exception as e:
                logging.exception(repr(e))

class Plugin:
    @classmethod
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        global loaded, locks

        plugin_name = cls.__module__.split('.')[0]
        plugin_instance = cls()
        logging.debug("loaded plugin %s as %s" % (plugin_name, plugin_instance))
        loaded[plugin_name] = plugin_instance

        for attr_name in plugin_instance.__dir__():
            if attr_name.startswith('on_'):
                cb = getattr(plugin_instance, attr_name, None)
                if cb is not None and callable(cb):
                    locks["%s::%s" % (plugin_name, attr_name)] = threading.Lock()


def toggle_plugin(name, enable=True):
    """
    Load or unload a plugin

    returns True if changed, otherwise False
    """
    import pwnagotchi
    from pwnagotchi.ui import view
    from pwnagotchi.utils import save_config

    global loaded, database

    if pwnagotchi.config:
        if not name in pwnagotchi.config['main']['plugins']:
            pwnagotchi.config['main']['plugins'][name] = dict()
        pwnagotchi.config['main']['plugins'][name]['enabled'] = enable

    if not enable and name in loaded:
        if getattr(loaded[name], 'on_unload', None):
            loaded[name].on_unload(view.ROOT)
        del loaded[name]
        if name in plugin_event_queues:
            plugin_event_queues[name].keep_going = False
            del plugin_event_queues[name]
        if pwnagotchi.config:
            save_config(pwnagotchi.config, '/etc/pwnagotchi/config.toml')
        return True

    if enable and name in database and name not in loaded:
        load_from_file(database[name])
        if name in loaded and pwnagotchi.config and name in pwnagotchi.config['main']['plugins']:
            loaded[name].options = pwnagotchi.config['main']['plugins'][name]
        one(name, 'loaded')
        time.sleep(3)
        if pwnagotchi.config:
            one(name, 'config_changed', pwnagotchi.config)
        one(name, 'ui_setup', view.ROOT)
        one(name, 'ready', view.ROOT._agent)
        if pwnagotchi.config:
            save_config(pwnagotchi.config, '/etc/pwnagotchi/config.toml')
        return True

    return False


def on(event_name, *args, **kwargs):
    global loaded, plugin_event_queues
    cb_name = 'on_%s' % event_name
    for plugin_name in loaded.keys():
        plugin = loaded[plugin_name]
        callback = getattr(plugin, cb_name, None)

        if callback is None or not callable(callback):
            continue

        if plugin_name not in plugin_event_queues:
            plugin_event_queues[plugin_name] = PluginEventQueue(plugin_name)

        plugin_event_queues[plugin_name].AddWork(event_name, *args, **kwargs)
        logging.debug("%s %s" % (plugin_name, cb_name))

def one(plugin_name, event_name, *args, **kwargs):
    global loaded, plugin_event_queues
    if plugin_name in loaded:
        plugin = loaded[plugin_name]
        cb_name = 'on_%s' % event_name
        callback = getattr(plugin, cb_name, None)
        if callback is not None and callable(callback):
            if plugin_name not in plugin_event_queues:
                plugin_event_queues[plugin_name] = PluginEventQueue(plugin_name)

            plugin_event_queues[plugin_name].AddWork(event_name, *args, **kwargs)


def load_from_file(filename):
    logging.debug("loading %s" % filename)
    plugin_name = os.path.basename(filename.replace(".py", ""))
    spec = importlib.util.spec_from_file_location(plugin_name, filename)
    instance = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(instance)
    if plugin_name not in plugin_event_queues:
        plugin_event_queues[plugin_name] = PluginEventQueue(plugin_name)
    return plugin_name, instance


def load_from_path(path, enabled=()):
    global loaded, database
    logging.debug("loading plugins from %s - enabled: %s" % (path, enabled))
    for filename in glob.glob(os.path.join(path, "*.py")):
        plugin_name = os.path.basename(filename.replace(".py", ""))
        database[plugin_name] = filename
        if plugin_name in enabled:
            try:
                load_from_file(filename)
            except Exception as e:
                logging.warning("error while loading %s: %s" % (filename, e))
                logging.debug(e, exc_info=True)

    return loaded


def load(config):
    try:
        enabled = [name for name, options in config['main']['plugins'].items() if
                   'enabled' in options and options['enabled']]

        # load default plugins
        load_from_path(default_path, enabled=enabled)

        # load custom ones
        custom_path = config['main']['custom_plugins'] if 'custom_plugins' in config['main'] else None
        if custom_path is not None:
            load_from_path(custom_path, enabled=enabled)

        # propagate options
        for name, plugin in loaded.items():
            if name in config['main']['plugins']:
                plugin.options = config['main']['plugins'][name]
            else:
                plugin.options = {}

        on('loaded')
        on('config_changed', config)
    except Exception as e:
        logging.exception(repr(e))
