#!/usr/bin/python3
#!/usr/bin/env python

import argparse
import io
import os
import pathlib
import pygubu
import pygubu.widgets.simpletooltip as tooltip
import re
import shutil
import struct
import subprocess
import tkinter as tk
import tkinter.ttk as ttk
import tempfile
import zipfile

have_pytube = False
try:
    import pytubefix as pytube
    have_pytube = True
except:
    True

from PIL import Image
from gamedb import games

from gba2psp import read_game, get_icon0, get_pic0, get_pic1, get_snd0, create_eboot

verbose = False
temp_files = []

PROJECT_PATH = pathlib.Path(__file__).parent
PROJECT_UI = PROJECT_PATH / "gba2psp-ui.ui"


class FinishedDialog(tk.Toplevel):
    def __init__(self, root):
        tk.Toplevel.__init__(self, root)
        label = tk.Label(self, text="Finished creating EBOOT")
        label.pack(fill="both", expand=True, padx=20, pady=20)

        button = tk.Button(self, text="Continue", command=self.destroy)
        button.pack(side="bottom")

class GBA2PSPApp:
    def __init__(self, master=None):
        self.myrect = None
        self.cue_files = None
        self.img_files = None
        self.game = None
        self.game_id = None
        self.icon0 = None
        self.icon0_raw = None
        self.icon0_tk = None
        self.pic0 = None
        self.pic0_raw = None
        self.pic0_path = None
        self.pic0_tk = None
        self.pic1 = None
        self.pic1_raw = None
        self.pic1_path = None
        self.pic1_tk = None
        self.pkgdir = None
        self.pic0_disabled = 'off'
        self.pic1_disabled = 'off'
        self.snd0_disabled = 'off'
        self.subdir='gba2psp-ui-work/'
        self.icon0_path = None
        
        self.master = master
        self.builder = builder = pygubu.Builder()
        builder.add_resource_path(PROJECT_PATH)
        builder.add_from_file(PROJECT_UI)
        self.mainwindow = builder.get_object("top_frame", master)

        callbacks = {
            'on_pic0_disabled': self.on_pic0_disabled,
            'on_pic1_disabled': self.on_pic1_disabled,
            'on_snd0_disabled': self.on_snd0_disabled,
            'on_path_changed': self.on_path_changed,
            'on_dir_changed': self.on_dir_changed,
            'on_create_eboot': self.on_create_eboot,
            'on_reset': self.on_reset,
        }

        builder.connect_callbacks(callbacks)

        # Tooltips
        self.disable_snd0 = builder.get_object("disable_snd0")
        tooltip.create(self.disable_snd0 , "Disable the SND0 audio that would play when the game icon is\nhighlighted on the XMB")
        self.disable_pic1 = builder.get_object("disable_pic1")
        tooltip.create(self.disable_pic1 , "Disable the background image that would show up on the XMB\nwhen the gameicon is highlighted")
        self.disable_pic0 = builder.get_object("disable_pic0")
        tooltip.create(self.disable_pic0 , "Disable the game logo that would show up on the XMB\nwhen the gameicon is highlighted")
        #self. = builder.get_object("")
        #tooltip.create(self. , "")
        
        self.init_data()
        try:
            self.read_prefs()
        except:
            True

    def __del__(self):
        global temp_files
        print('Delete temporary files') if verbose else None
        for f in temp_files:
            print('Deleting temp/dir file', f) if verbose else None
            try:
                os.unlink(f)
            except:
                try:
                    os.rmdir(f)
                except:
                    True
        temp_files = []  

    def init_data(self):
        global temp_files
        if temp_files:
            for f in temp_files:
                try:
                    os.unlink(f)
                except:
                    try:
                        os.rmdir(f)
                    except:
                        True

        temp_files = []  
        temp_files.append(self.subdir)
        shutil.rmtree(self.subdir, ignore_errors=True)
        os.mkdir(self.subdir)

        self.cue_files = []
        self.img_files = []
        self.game = None
        self.game_id = None
        self.icon0 = None
        self.icon0_raw = None
        self.icon0_tk = None
        self.pic0 = None
        self.pic0_raw = None
        self.pic0_path = None
        self.pic0_tk = None
        self.pic1 = None
        self.pic1_raw = None
        self.pic1_path = None
        self.pic1_tk = None
        self.preview_tk = None
        self.builder.get_object('disc1', self.master).config(filetypes=[('Image files', ['.gba', '.zip']), ('All Files', ['*.*', '*'])])
        self.builder.get_variable('disc1_variable').set('')
        self.builder.get_object('create_button', self.master).config(state='disabled')
        self.builder.get_variable('title_variable').set('')

    def update_prefs(self):
        with open('gba2psp-ui.config', "w") as f:
            f.write('%s:%s\n' % ('pic0_disabled', self.builder.get_variable('pic0_disabled_variable').get()))
            f.write('%s:%s\n' % ('pic1_disabled', self.builder.get_variable('pic1_disabled_variable').get()))
            f.write('%s:%s\n' % ('snd0_disabled', self.builder.get_variable('snd0_disabled_variable').get()))
            f.write('%s:%s\n' % ('dir', self.builder.get_variable('pkgdir_variable').get()))


    def read_prefs(self):
        with open('gba2psp-ui.config', "r") as f:
            for x in f.read().splitlines():
                key, val =  x.split(':')
                if key == 'pic0_disabled':
                    self.builder.get_variable('pic0_disabled_variable').set(val)
                    self.disable_pic0 = val
                if key == 'pic1_disabled':
                    self.builder.get_variable('pic1_disabled_variable').set(val)
                    self.disable_pic1 = val
                if key == 'snd0_disabled':
                    self.builder.get_variable('snd0_disabled_variable').set(val)
                    self.disable_snd0 = val
                if key == 'dir':
                    self.builder.get_variable('pkgdir_variable').set(val)
                    self.pkgdir = val


    def update_assets(self, update_icon0=True, update_pic0=True, update_pic1=True):
        if not self.game_id:
            return

        if update_icon0:
            print('Fetching ICON0') if verbose else None
            self.icon0 = None
            self.icon0_raw = None
            if not self.icon0 and 'icon0' in games[self.game_id]:
                self.icon0_raw = get_icon0(games[self.game_id]['icon0'])
                if self.icon0_raw:
                    self.icon0 = Image.open(io.BytesIO(self.icon0_raw))
            if self.icon0:
                temp_files.append(self.subdir + 'ICON0.PNG')
                self.icon0.resize((80,80), Image.Resampling.HAMMING).save(self.subdir + 'ICON0.PNG')
                self.icon0_tk = tk.PhotoImage(file = self.subdir + 'ICON0.PNG')
                c = self.builder.get_object('icon0_canvas', self.master)
                c.create_image(0, 0, image=self.icon0_tk, anchor='nw')
 
        if self.snd0_disabled == 'off':
            snd0 = None
            print('Fetching SND0') if verbose else None
            if not snd0 and self.game_id in games and 'snd0' in games[self.game_id]:
                snd0 = games[self.game_id]['snd0']
                
        if update_pic0:
            print('Fetching PIC0') if verbose else None
            self.pic0 = None
            self.pic0_raw = None
            if not self.pic0:
                self.pic0_raw = get_pic0(games[self.game_id]['pic0'])
                if self.pic0_raw:
                    self.pic0 = Image.open(io.BytesIO(self.pic0_raw))
            if self.pic0:
                temp_files.append(self.subdir + 'PIC0.PNG')
                self.pic0.resize((128,80), Image.Resampling.HAMMING).save(self.subdir + 'PIC0.PNG')
                self.pic0_tk = tk.PhotoImage(file = self.subdir + 'PIC0.PNG')
                c = self.builder.get_object('pic0_canvas', self.master)
                c.create_image(0, 0, image=self.pic0_tk, anchor='nw')
        
        if update_pic1:
            print('Fetching PIC1') if verbose else None
            self.pic1 = None
            self.pic1_raw = None
            if not self.pic1:
                self.pic1_raw = get_pic1(games[self.game_id]['pic1'])
                if self.pic1_raw:
                    self.pic1 = Image.open(io.BytesIO(self.pic1_raw))
            if self.pic1:
                temp_files.append(self.subdir + 'PIC1.PNG')
                self.pic1.resize((128,80), Image.Resampling.HAMMING).save(self.subdir + 'PIC1.PNG')
                self.pic1_tk = tk.PhotoImage(file = self.subdir + 'PIC1.PNG')
                c = self.builder.get_object('pic1_canvas', self.master)
                c.create_image(0, 0, image=self.pic1_tk, anchor='nw')

        self.update_preview()
        
    def on_path_changed(self, event):
        gba_file = event.widget.cget('path')
        if not len(gba_file):
            return

        self.update_prefs()

        self.master.config(cursor='watch')
        self.master.update()
        print('Processing', gba_file)  if verbose else None
        disc = event.widget.cget('title')
        print('Disc', disc)  if verbose else None

        print('Scanning for Game ID') if verbose else None
        self.game = read_game(gba_file)
        game_id = bytearray(self.game[0xa0:0xb0])
        for i in range(16):
            if game_id[i] == 0x00:
                game_id[i] = 0x20
        game_id = game_id.decode()

        print('GameID: [%s]' % game_id)
        print('Title:', games[game_id]['title'])

        self.game_id = game_id

        self.builder.get_variable('title_variable').set(games[game_id]['title'])

        self.update_assets()
            
        self.builder.get_object('create_button', self.master).config(state='normal')
        self.update_preview()

        print('Finished processing disc') if verbose else None
        self.master.config(cursor='')

    def update_preview(self):
        def has_transparency(img):
            if img.info.get("transparency", None) is not None:
                return True
            if img.mode == "P":
                transparent = img.info.get("transparency", -1)
                for _, index in img.getcolors():
                    if index == transparent:
                        return True
            elif img.mode == "RGBA":
                extrema = img.getextrema()
                if extrema[3][0] < 255:
                    return True

                return False

        if not self.game_id:
            return

        if self.pic0_disabled == 'on':
            _pic0 = None
        else:
            _pic0 = self.pic0
        if self.pic1_disabled == 'on':
            _pic1 = Image.new('RGBA', (382,216), (0,0,0))
            _pic1.putalpha(0)
        else:
            _pic1 = self.pic1

        if _pic0 and self.pic0.mode == 'P':
            _pic0 = _pic0.convert(mode='RGBA')
        c = self.builder.get_object('preview_canvas', self.master)
        if _pic1:
            p1 = _pic1.resize((382,216), Image.Resampling.HAMMING)
        else:
            p1 = Image.new('RGBA', (382,216), (0,0,0))
        p1 = p1.convert('RGBA')
        if _pic0:
            p0 = _pic0.resize((int(p1.size[0] * 0.55) , int(p1.size[1] * 0.58)), Image.Resampling.HAMMING)
            if has_transparency(p0):
                Image.Image.paste(p1, p0, box=(148,79), mask=p0)
            else:
                Image.Image.paste(p1, p0, box=(148,79))
        if self.icon0:
            i0 = self.icon0.resize((int(p1.size[1] * 0.25) , int(p1.size[1] * 0.25)), Image.Resampling.HAMMING)
            if has_transparency(i0):
                Image.Image.paste(p1, i0, box=(36,81), mask=i0)
            else:
                Image.Image.paste(p1, i0, box=(36,81))
        temp_files.append(self.subdir + 'PREVIEW.PNG')
        p1.save(self.subdir + 'PREVIEW.PNG')
        self.preview_tk = tk.PhotoImage(file = self.subdir + 'PREVIEW.PNG')
        c = self.builder.get_object('preview_canvas', self.master)
        c.create_image(0, 0, image=self.preview_tk, anchor='nw')
        

    def on_pic0_disabled(self):
        self.pic0_disabled = self.builder.get_variable('pic0_disabled_variable').get()
        self.update_preview()
        self.update_prefs()

    def on_pic1_disabled(self):
        self.pic1_disabled = self.builder.get_variable('pic1_disabled_variable').get()
        self.update_preview()
        self.update_prefs()

    def on_snd0_disabled(self):
        self.snd0_disabled = self.builder.get_variable('snd0_disabled_variable').get()
        self.update_prefs()

    def on_dir_changed(self, event):
        self.pkgdir = event.widget.cget('path')
        self.update_prefs()

    def on_create_eboot(self):        
        pkgdir = self.builder.get_variable('pkgdir_variable').get()
        title = self.builder.get_variable('title_variable').get()
        print('Creating EBOOT')
        print('GAME', self.game_id)
        print('TITLE', title)

        self.master.config(cursor='watch')
        self.master.update()

        ebootdir = self.pkgdir if self.pkgdir else '.'

        td = tempfile.TemporaryDirectory(prefix='gba2psp-ui-work')
        snd0 = None
        if 'snd0' in games[self.game_id]:
            snd0 = get_snd0(games[self.game_id]['snd0'], td.name)

        create_eboot(self.game, self.game_id, self.icon0_raw, self.pic0_raw, self.pic1_raw, snd0, self.pkgdir)
        self.master.config(cursor='')

        d = FinishedDialog(self.master)
        self.master.wait_window(d)
        self.init_data()

    def on_reset(self):
        self.init_data()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', action='store_true', help='Verbose')
    args = parser.parse_args()

    if args.v:
        verbose = True

    root = tk.Tk()
    app = GBA2PSPApp(root)
    root.title('GBA2PSP')
    root.mainloop()
    
