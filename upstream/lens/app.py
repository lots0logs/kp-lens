#
# Copyright 2012-2014 "Korora Project" <dev@kororaproject.org>
#
# This program is free software: you can redistribute it and/or modify
# it under the temms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#

import dbus
import logging
import os
import subprocess
import traceback

from lens.view import View
from lens.thread import Thread, ThreadManager

class App():
  @staticmethod
  def __get_toolkit(name, exact=False):
    #: defines the list of Lens backends to be preloaded for auto-detection
    __toolkits = {
      'gtk':  ['lens.appgtk',  'ViewGtk' ],
      'qt':   ['lens.appqt',   'ViewQt'  ],
      'qt5':  ['lens.appqt5',  'ViewQt5' ]
    }

    __tk_error = []

    if name in __toolkits:
      try:
        __tk = __toolkits[name]
        __module = __import__(__tk[0], globals(), locals(), [__tk[1]], 0)
        return getattr(__module, __tk[1], None)

      except:
        if exact:
          raise Exception('Toolkit %s is not implemented or could not be loaded.' % (name))

        else:
          #traceback.print_exc()
          __tk_error.append(name)

    for k in __toolkits:
      if k in __tk_error:
        continue

      try:
        print("Loading fallback: %s" % (k))
        __tk = __toolkits[name]
        __module = __import__(__tk[0], globals(), locals(), [__tk[1]], 0)
        return getattr(__module, __tk[1], None)
      except:
        __tk_error.append(name)

    raise Exception('No fallback toolkits implemented or loaded.')

  """The app object implements a Lens application and acts as the central
  object. Once created it will act as a central registry for the view
  toolkit abstraction, thread management, signal handling and much more.

  :param toolkit: force the toolkit to use. If set to `None` the toolkit
                  will be auto detected.
  :param toolkit_hint: hint to the preferred toolkit if the auto detection
                       fails to determine the active toolkit.
  :param name: the name of the Lens application. Also shown in the Lens
               application window's title bar.
  :param width: the width of the Lens applciation window. Defaults to 640.
  :param height the height of the Lens applciation window. Defaults to 480.
  """
  def __init__(self, toolkit=None, toolkit_hint='gtk', name="MyLensApp", width=640, height=480, inspector=False, *args, **kwargs):
    self._logger = logging.getLogger('Lens.App')

    self._app_name = name
    self._app_width = width
    self._app_height = height

    # dbus
    self._dbus_session = None
    self._dbus_system = None

    # determine the preferred toolkit to use and build the appropiate LensView
    if toolkit is None:
      toolkit = self.__get_desktop_toolkit_hint(toolkit_hint.lower())

    # attempt to load the preffered
    toolkit_klass = App.__get_toolkit(toolkit.lower())
    self._logger.debug('Using %s toolkit' % (toolkit.lower()))

    self._lv = toolkit_klass(name=name, width=width, height=height, inspector=inspector)

    #: find lens data path
    base = None
    for d in ["/usr/share/lens", "lens-data"]:
      if os.path.exists(d):
        if d.startswith('/'):
          base = d
        else:
          base = os.path.join(os.getcwd(), d)
        break

    if base is None:
      raise Exception('Unable to locate lens base data for UI components.')

    self._lv._uri_lens_base = 'file://' + base + '/'

    self._logger.debug("Using lens data path: %s" % self._lv._uri_lens_base)

    #: store an app reference to the thread manager
    self.threads = self._lv._manager

    #: manage directory namespaces for local app data
    self.namespaces = []

  def __get_desktop_toolkit_hint(self, hint):
    def __is_running(process):
      try:
        # Linux/Unix
        s = subprocess.Popen(["ps", "axw"], stdout=subprocess.PIPE)
      except:
        # Windows
        s.Popen(["tasklist", "/v"], stdout=subprocess.PIPE)

      for x in s.stdout:
        if process in x.decode('utf-8'):
          return True

      return False

    toolkit = hint

    if os.environ.get('KDE_FULL_SESSION') == 'true':
      toolkit = 'qt'

    elif os.environ.get('GNOME_DESKTOP_SESSION_ID'):
      toolkit = 'gtk'

    elif __is_running("xfce-mcs-manage") or __is_running('xfce4-session'):
      toolkit = "gtk"

    elif __is_running("ksmserver"):
      toolkit = 'qt'

    return toolkit

  def _dbus_async_cb(self, name):
    def decorator(*args, **kwargs):
      error = None

      # check for DBus exceptions
      if len(args) == 1 and isinstance(args[0], dbus.DBusException):
        error = args[0]

      self._lv.emit('dbus.'+ name, error, *args)

    return decorator

  @property
  def name(self):
    return self._app_name

  @name.setter
  def name(self, name):
    self._app_name = name

    # update window title on app name change
    self._lv.set_title(self._app_name)

  # DEPRECATE:
  # remove "manager" property in 1.0.0
  @property
  def manager(self):
    self._logger.warn('The "manager" property is deprecated, use "threads" instead.')
    return self.threads

  def close(self):
    self._lv.close()

  def connect(self, name):
    """A decorator that is used to register a callback for
       a given signal. Example usage::

         @app.connect('hello')
         def hello_cb():
           print("Hi!")

    :param name: the name of the signal to subscribe to
    """
    def decorator(f):
      self.on(name, f)
      return f

    return decorator


  # DBus helpers
  def dbus_async_call(self, signal, fn_method, *args):
    if not isinstance(fn_method, dbus.proxies._DeferredMethod) and \
       not isinstance(fn_method, dbus.proxies._ProxyMethod):
       raise Exception('Not a valid deferred/proxy method.')

    _cb = self._dbus_async_cb(signal)

    return fn_method(*args, reply_handler=_cb, error_handler=_cb)

  def dbus_interface(self, *args, **kwargs):
    return dbus.Interface(*args, **kwargs)

  def dbus_session(self):
    if self._dbus_session is None:
      self._dbus_session = dbus.SessionBus()

    return self._dbus_session

  def dbus_session_interface(self, org, path, interface=None):
    if interface is None:
      interface = org

    proxy = self.dbus_session().get_object(org, path)
    return self.dbus_interface(proxy, interface)

  def dbus_system(self):
    if self._dbus_system is None:
      self._dbus_system = dbus.SystemBus()

    return self._dbus_system

  def dbus_system_interface(self, org, path, interface=None):
    if interface is None:
      interface = org

    proxy = self.dbus_system().get_object(org, path)
    return self.dbus_interface(proxy, interface)

  def emit(self, name, *args):
    self._lv.emit_js(name, *args)

  def load_ui(self, uri):
    """Load the UI from the specified URI. The URI is a relative path within
    the defined application namespace.

    :param uri: the uri to the entry page of the UI.
    """
    for d in self.namespaces:
      _uri = os.path.abspath(os.path.join(d, uri))

      if os.path.exists(_uri):
        self._logger.debug("Loading URI: %s" % _uri)

        return self._lv.load_uri('file://' + _uri)

    raise Exception("Unable to locate application in the defined namespace.");

  def on(self, name, callback):
    self._lv.on(name, callback)

  def resize(self, width, height):
    """Resizes the application window.

    :param width: the requested width for the application window. If set to
                  `None`, the width won't be changed.
    :param height: the requested height for the application window. If set to
                  `None`, the height won't be changed.
    """
    if width is not None:
      self._app_width = width

    if height is not None:
      self._app_height = height

    self._lv.set_size(self._app_width, self._app_height)

  def set_title(self, title):
    self._lv.set_title(title)

  def start(self):
    self._lv._run()

