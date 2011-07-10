#        +-----------------------------------------------------------------------------+
#        | GPL                                                                         |
#        +-----------------------------------------------------------------------------+
#        | Copyright (c) Brett Smith <tanktarta@blueyonder.co.uk>                      |
#        |                                                                             |
#        | This program is free software; you can redistribute it and/or               |
#        | modify it under the terms of the GNU General Public License                 |
#        | as published by the Free Software Foundation; either version 2              |
#        | of the License, or (at your option) any later version.                      |
#        |                                                                             |
#        | This program is distributed in the hope that it will be useful,             |
#        | but WITHOUT ANY WARRANTY; without even the implied warranty of              |
#        | MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the               |
#        | GNU General Public License for more details.                                |
#        |                                                                             |
#        | You should have received a copy of the GNU General Public License           |
#        | along with this program; if not, write to the Free Software                 |
#        | Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA. |
#        +-----------------------------------------------------------------------------+
 
import gnome15.g15util as g15util
import gnome15.g15driver as g15driver
import gnome15.g15screen as g15screen
import cairo
import gtk
import os
import logging
import gconf
logger = logging.getLogger("background")


# Plugin details - All of these must be provided
id="background"
name="Wallpaper"
description="Use an image for the LCD background"
author="Brett Smith <tanktarta@blueyonder.co.uk>"
copyright="Copyright (C)2010 Brett Smith"
site="http://www.gnome15.org/"
has_preferences=True
unsupported_models = [ g15driver.MODEL_G110, g15driver.MODEL_G11 ]

def create(gconf_key, gconf_client, screen):
    return G15Background(gconf_key, gconf_client, screen)

def show_preferences(parent, driver, gconf_client, gconf_key):
    G15BackgroundPreferences(parent, driver, gconf_client, gconf_key)
    
class G15BackgroundPreferences():
    
    def __init__(self, parent, driver, gconf_client, gconf_key):
        
        widget_tree = gtk.Builder()
        widget_tree.add_from_file(os.path.join(os.path.dirname(__file__), "background.glade"))
        
        self.gconf_client = gconf_client
        self.gconf_key = gconf_key
        
        # Widgets
        dialog = widget_tree.get_object("BackgroundDialog")
        dialog.set_transient_for(parent)        
        g15util.configure_radio_from_gconf(gconf_client, gconf_key + "/type", [ "UseDesktop", "UseFile" ], [ "desktop", "file" ], "desktop", widget_tree, True)
        g15util.configure_combo_from_gconf(gconf_client, gconf_key + "/style", "StyleCombo", "zoom", widget_tree)
        widget_tree.get_object("UseDesktop").connect("toggled", self.set_available, widget_tree)
        widget_tree.get_object("UseFile").connect("toggled", self.set_available, widget_tree)
        
        # Currently, only GNOME is supported for getting the desktop background
        if not "gnome" == g15util.get_desktop():
            widget_tree.get_object("UseFile").set_active(True)
        
        # The file chooser
        chooser = gtk.FileChooserDialog("Open..",
                               None,
                               gtk.FILE_CHOOSER_ACTION_OPEN,
                               (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                                gtk.STOCK_OPEN, gtk.RESPONSE_OK))
        chooser.set_default_response(gtk.RESPONSE_OK)
        
        filter = gtk.FileFilter()
        filter.set_name("Images")
        filter.add_mime_type("image/png")
        filter.add_mime_type("image/jpeg")
        filter.add_mime_type("image/gif")
        filter.add_pattern("*.png")
        filter.add_pattern("*.jpg")
        filter.add_pattern("*.jpeg")
        filter.add_pattern("*.gif")
        chooser.add_filter(filter)
        
        filter = gtk.FileFilter()
        filter.set_name("All files")
        filter.add_pattern("*")
        chooser.add_filter(filter)
        
        chooser_button = widget_tree.get_object("FileChooserButton")        
        chooser_button.dialog = chooser        
        chooser_button.connect("file-set", self.file_set)
        widget_tree.connect_signals(self)
        bg_img = gconf_client.get_string(gconf_key + "/path")
        if bg_img == None:
            bg_img = ""
        chooser_button.set_filename(bg_img)
        self.set_available(None, widget_tree)
        dialog.run()
        dialog.hide()
    
    def set_available(self, widget, widget_tree):
        widget_tree.get_object("FileChooserLabel").set_sensitive(widget_tree.get_object("UseFile").get_active())
        widget_tree.get_object("FileChooserButton").set_sensitive(widget_tree.get_object("UseFile").get_active())
        
    def file_set(self, widget):
        self.gconf_client.set_string(self.gconf_key + "/path", widget.get_filename())
        
        
class G15BackgroundPainter(g15screen.Painter):
    
    def __init__(self):
        g15screen.Painter.__init__(self, g15screen.BACKGROUND_PAINTER, -9999)
        self.background_image = None
        
    def paint(self, canvas):
        if self.background_image != None:
            canvas.set_source_surface(self.background_image, 0.0, 0.0)
            canvas.paint()
        
        
class G15Background():
    
    def __init__(self, gconf_key, gconf_client, screen):
        self.screen = screen
        self.gconf_client = gconf_client
        self.gconf_key = gconf_key
        self.target_surface = None
        self.target_context = None
        self.gconf_client.add_dir('/desktop/gnome/background', gconf.CLIENT_PRELOAD_NONE)
    
    def activate(self):
        self.bg_img = None
        self.this_image = None
        self.current_style = None
        self.notify_handlers = []
        self.painter = G15BackgroundPainter()
        self.screen.painters.append(self.painter)
        self.notify_handlers.append(self.gconf_client.notify_add(self.gconf_key + "/path", self.config_changed))
        self.notify_handlers.append(self.gconf_client.notify_add(self.gconf_key + "/type", self.config_changed))
        self.notify_handlers.append(self.gconf_client.notify_add(self.gconf_key + "/style", self.config_changed))
        
        # Monitor desktop specific configuration for wallpaper changes
        if "gnome" == g15util.get_desktop():
            self.notify_handlers.append(self.gconf_client.notify_add("/desktop/gnome/background/picture_filename", self.config_changed))
        
        self._do_config_changed()
    
    def deactivate(self):
        self.screen.painters.remove(self.painter)
        for h in self.notify_handlers:
            self.gconf_client.notify_remove(h);
        self.screen.redraw()
        
    def config_changed(self, client, connection_id, entry, args):
        self._do_config_changed()
        
    def destroy(self):
        pass
            
    '''
    Private
    ''' 
    def _do_config_changed(self):
        # Get the configuration
        screen_size = self.screen.size
        self.bg_img = None
        bg_type = self.gconf_client.get_string(self.gconf_key + "/type")
        if bg_type == None:
            bg_type = "desktop"
        bg_style = self.gconf_client.get_string(self.gconf_key + "/style")
        if bg_style == None:
            bg_style = "zoom"
        
        if bg_type == "desktop":
            # Get the current background the desktop is using if possible
            desktop_env = g15util.get_desktop()
            if "gnome" == desktop_env:
                self.bg_img = self.gconf_client.get_string("/desktop/gnome/background/picture_filename")
            else:
                logger.warning("User request wallpaper from the desktop, but the desktop environment is unknown. Please report this bug to the Gnome15 project")
        
        if self.bg_img == None:
            # Use the file
            self.bg_img = self.gconf_client.get_string(self.gconf_key + "/path")
            
        # Fallback to the default provided image
        if self.bg_img == None:
            self.bg_img = os.path.join(os.path.dirname(__file__), "background-%dx%d.png" % ( screen_size[0], screen_size[1] ) )
            
        # Load the image 
        if self.bg_img != self.this_image or bg_style != self.current_style:
            self.this_image = self.bg_img
            self.current_style = bg_style
            if os.path.exists(self.bg_img):
                img_surface = g15util.load_surface_from_file(self.bg_img)
                sx = float(screen_size[0]) / img_surface.get_width()
                sy = float(screen_size[1]) / img_surface.get_height()  
                surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, screen_size[0], screen_size[1])
                context = cairo.Context(surface)
                context.save()
                if bg_style == "zoom":
                    scale = max(sx, sy)
                    context.scale(scale, scale)
                    context.set_source_surface(img_surface)
                    context.paint()
                elif bg_style == "stretch":              
                    context.scale(sx, sy)
                    context.set_source_surface(img_surface)
                    context.paint()
                elif bg_style == "scale":  
                    x = ( screen_size[0] - img_surface.get_width() * sy ) / 2   
                    context.translate(x, 0)         
                    context.scale(sy, sy)
                    context.set_source_surface(img_surface)
                    context.paint()
                elif bg_style == "center":        
                    x = ( screen_size[0] - img_surface.get_width() ) / 2
                    y = ( screen_size[1] - img_surface.get_height() ) / 2
                    context.translate(x, y)
                    context.set_source_surface(img_surface)
                    context.paint()
                elif bg_style == "tile":
                    context.set_source_surface(img_surface)
                    context.paint()
                    y = 0
                    x = img_surface.get_width()
                    while y < screen_size[1] + img_surface.get_height():
                        if x >= screen_size[1] + img_surface.get_width():
                            x = 0
                            y += img_surface.get_height()
                        context.restore()
                        context.save()
                        context.translate(x, y)
                        context.set_source_surface(img_surface)
                        context.paint()
                        x += img_surface.get_width()
                    
                context.restore()
                self.painter.background_image = surface
            else:
                self.painter.background_image = None
                
                
        self.screen.redraw()