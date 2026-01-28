#! python2

# -= ToDo =-
#  - Tidy up code

import wx, wx.lib.dialogs, wx.html2, os, sys, thread, libnas, json, tempfile, time, datetime, shutil, win32gui, win32com.client, urllib

def human_readable_size(size):
  if size > (1024**3):
    return '%.3f GB' % (float(size)/(1024**3))
  if size > (1024**2):
    return '%.3f MB' % (float(size)/(1024**2))
  if size > (1024):
    return '%.3f KB' % (float(size)/(1024))
  return str(size) + ' B'

class Redirect_Output(object):
  def __init__(self,ctrl): self.out=ctrl
  def write(self,str): self.out.SetInsertionPointEnd() ; self.out.WriteText(str)

class Main_Window(wx.Frame):
  def __init__(self, parent, id, name, NAS):
    super(Main_Window, self).__init__(parent, title = name, size = (800,600))
    self.name = name
    self.NAS = NAS
    self.current_path = ''
    self.clipboard = None
    self.history = []
    self.current_history = 0
    self.max_history = 100
    self.cache_dir = os.path.join(tempfile.gettempdir(), name+'-cache')
    self.icon = wx.Icon(name+'.ico', wx.BITMAP_TYPE_ICO)
    self.SetIcon(self.icon)
    self.SetBackgroundColour(wx.WHITE)
    self.panel = wx.Panel(self)
    sizer = wx.BoxSizer(wx.VERTICAL)
    self.metadata = {}

    menubar = wx.MenuBar()
    file_menu = wx.Menu()
    mitem = file_menu.Append(wx.ID_ANY, 'Upload')
    self.Bind(wx.EVT_MENU, self.crupdate_file_picker, mitem)
    mitem = file_menu.Append(wx.ID_ANY, 'New Folder')
    self.Bind(wx.EVT_MENU, self.new_folder, mitem)
    mitem = file_menu.Append(wx.ID_ANY, 'Search')
    self.Bind(wx.EVT_MENU, self.search, mitem)
    mitem = file_menu.Append(wx.ID_ANY, 'Clear Cache')
    self.Bind(wx.EVT_MENU, self.clear_cache, mitem)
    mitem = file_menu.Append(wx.ID_EXIT, 'Exit')
    self.Bind(wx.EVT_MENU, self.on_exit, mitem)
    menubar.Append(file_menu, 'File')
    nerd_menu = wx.Menu()
    mitem = nerd_menu.Append(wx.ID_ANY, 'Metadata')
    self.Bind(wx.EVT_MENU, self.show_metadata, mitem)
    mitem = nerd_menu.Append(wx.ID_ANY, 'Sanity Report')
    self.Bind(wx.EVT_MENU, self.show_sanity, mitem)
    mitem = nerd_menu.Append(wx.ID_ANY, 'Version')
    self.Bind(wx.EVT_MENU, self.show_version, mitem)
    menubar.Append(nerd_menu, 'Nerd Stuff')
    self.SetMenuBar(menubar)

    address_sizer = wx.BoxSizer(wx.HORIZONTAL)
    button_back = wx.ArtProvider_GetBitmap(wx.ART_GO_BACK, wx.ART_BUTTON, (16,16))
    button_back = wx.BitmapButton(self.panel, bitmap=button_back)
    button_back.Bind(wx.EVT_BUTTON, self.back)
    address_sizer.Add(button_back, flag=wx.ALL, border=5)
    bmp_forward = wx.ArtProvider_GetBitmap(wx.ART_GO_FORWARD, wx.ART_BUTTON, (16,16))
    button_forward = wx.BitmapButton(self.panel, bitmap=bmp_forward)
    button_forward.Bind(wx.EVT_BUTTON, self.forward)
    address_sizer.Add(button_forward, flag=wx.ALL, border=5)
    bmp_up = wx.ArtProvider_GetBitmap(wx.ART_GO_DIR_UP, wx.ART_BUTTON, (16,16))
    button_up = wx.BitmapButton(self.panel, bitmap=bmp_up)
    button_up.Bind(wx.EVT_BUTTON, self.up)
    address_sizer.Add(button_up, flag=wx.ALL, border=5)
    self.address_bar = wx.TextCtrl(self.panel, style=wx.TE_PROCESS_ENTER)
    self.address_bar.Bind(wx.EVT_TEXT_ENTER, self.go)
    address_sizer.Add(self.address_bar, proportion=1, flag=wx.EXPAND|wx.ALL, border=5)
    button_go = wx.Button(self.panel, label = 'Go / Reload', style = wx.BU_EXACTFIT)
    button_go.Bind(wx.EVT_BUTTON, self.go)
    address_sizer.Add(button_go, flag=wx.ALL, border=5)

    self.browser_splitter = wx.SplitterWindow(self.panel, -1)
    self.browser_splitter.SetBackgroundColour(wx.WHITE)
    self.dir_tree = wx.TreeCtrl(self.browser_splitter)
    root = self.dir_tree.AddRoot('<Root>')
    self.Bind(wx.EVT_TREE_ITEM_ACTIVATED, self.OnTreeClick, self.dir_tree)
    self.Bind(wx.EVT_TREE_ITEM_RIGHT_CLICK, self.OnRightClick, self.dir_tree)
    self.file_list = wx.ListCtrl(self.browser_splitter, style=wx.LC_ICON)
    self.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.OnListClick, self.file_list)
    self.Bind(wx.EVT_LIST_ITEM_RIGHT_CLICK, self.OnRightClick, self.file_list)
    self.Bind(wx.EVT_CONTEXT_MENU, self.OnRightClick, self.file_list)
    self.Bind(wx.EVT_LIST_BEGIN_DRAG, self.OnDragOut)
    self.file_list.SetDropTarget(CrupdateFileDropTarget(self))
    self.browser_splitter.SplitVertically(self.dir_tree, self.file_list)
    self.browser_splitter.SetSashPosition(200)

    il = wx.ImageList(48, 48)
    self.icon_folder = il.Add(wx.ArtProvider.GetBitmap(wx.ART_FOLDER, wx.ART_MENU, (48,48)))
    self.icon_file = il.Add(wx.ArtProvider.GetBitmap(wx.ART_NORMAL_FILE, wx.ART_MENU, (48,48)))
    self.icon_photo = il.Add(wx.Bitmap('photo.ico', type=wx.BITMAP_TYPE_ICO))
    self.file_list.SetImageList(il, wx.IMAGE_LIST_NORMAL)
    sil = wx.ImageList(16, 16)
    self.ico_folder = sil.Add(wx.ArtProvider.GetBitmap(wx.ART_FOLDER, wx.ART_MENU, (16,16)))
    self.dir_tree.SetImageList(sil)
    root_ico = sil.Add(wx.ArtProvider.GetBitmap(wx.ART_HARDDISK, wx.ART_MENU, (16,16)))
    self.dir_tree.SetItemImage(root, root_ico)
    self.il = (il,sil) # Need to store these so they don't get gc'd

    logctrl = wx.TextCtrl(self.panel, -1, style=wx.TE_MULTILINE|wx.TE_READONLY, size=(60,60))
    sys.stdout, sys.stderr = Redirect_Output(logctrl), Redirect_Output(logctrl)

    sizer.Add(address_sizer, flag = wx.EXPAND)
    sizer.Add(self.browser_splitter, flag = wx.EXPAND, proportion=1)
    sizer.Add(logctrl, flag = wx.EXPAND)

    self.panel.SetSizerAndFit(sizer)
    self.Centre()
    self.Show(True)
    self.go()

  def on_exit(self, evt):
    self.Close()

  def msgbox(self, type, msg):
    dlg = wx.MessageDialog(self, msg, self.name, wx.OK | type)
    dlg.ShowModal()
    dlg.Destroy()

  def yesnobox(self, msg):
    dlg = wx.MessageBox(msg, self.name, wx.YES_NO | wx.ICON_EXCLAMATION)
    return (dlg == wx.YES)

  def text_entry(self, caption, prompt, default=''):
    dlg = wx.TextEntryDialog(self, prompt, caption=caption, defaultValue=default)
    dlg.ShowModal()
    val = dlg.GetValue()
    dlg.Destroy()
    return val

  def handle_NAS_Error(self, ex):
    if type(ex) == libnas.NAS_Error:
      self.msgbox(wx.ICON_ERROR, 'Error: ' + ex.message)
    elif type(ex) == libnas.NAS_Timeout:
      self.msgbox(wx.ICON_ERROR, 'The request timed out.\n' +
                  'Please check your internet connection and try again.')
    raise ex

  def is_photo(self, path):
    return (
            path.lower().endswith('.bmp') or
            path.lower().endswith('.jpg') or
            path.lower().endswith('.jpeg') or
            path.lower().endswith('.png')
           )

  def download_or_get_from_cache(self, path):
    m = self.metadata[path]
    cache_file = (os.path.splitext(path)[0].split('/')[-1] +
                  ' (' + m['SHA1'] + ')' + os.path.splitext(path)[1])
    cach_path = os.path.join(self.cache_dir, cache_file)
    if os.path.exists(cach_path):
      chash = self.NAS.hash_file(cach_path)
      if m['SHA1'] == chash:
        return cach_path
      else:
        os.remove(cach_path)
    t = tempfile.mktemp()
    s = {'size': m['size'], 'last_check':time.time()}
    def cb(progress):
      if (time.time()-s['last_check']) > 10:
        print (
               'Downloading ' + path +
               ('     %.3f%%     (' % (100.0*progress/s['size'])) +
               human_readable_size(progress) + ' of ' +
               human_readable_size(s['size']) + ')'
              )
        s['last_check'] = time.time()
    try: self.NAS.download_file(path, t, callback=cb)
    except Exception as ex: self.handle_NAS_Error(ex)
    try:
      os.mkdir(self.cache_dir)
    except OSError:
      pass
    os.rename(t, cach_path)
    return cach_path

  def show_metadata(self, evt):
    def async(self):
      print 'Getting metadata...'
      try: md = self.NAS.metadata()
      except Exception as ex: self.handle_NAS_Error(ex)
      self.metadata = md['files']
      str = ('-= Metadata =-\n\n' +
             json.dumps(md,sort_keys=True,
                        indent=2, separators=(',', ': ')))
      dlg = wx.lib.dialogs.ScrolledMessageDialog(self, str, self.name)
      dlg.ShowModal()
      dlg.Destroy()
    thread.start_new_thread(async, (self,))

  def show_sanity(self, evt):
    def async(self):
      try: self.msgbox(0, self.NAS.sanity())
      except Exception as ex: self.handle_NAS_Error(ex)
    thread.start_new_thread(async, (self,))

  def show_version(self, evt):
    def async(self):
      try: self.msgbox(0, self.NAS.version())
      except Exception as ex: self.handle_NAS_Error(ex)
    thread.start_new_thread(async, (self,))

  def go(self, evt=None, record_history=True):
    def async(self):
      path = self.address_bar.GetValue()
      if path.endswith('/'):
        path = path[:-1]
        self.address_bar.SetValue(path)
      print 'Listing Dir: ' + path
      try: ls = self.NAS.list_dir(path)
      except Exception as ex: self.handle_NAS_Error(ex)
      if record_history:
        self.history = self.history[self.current_history:]
        self.history = [path] + self.history[:self.max_history]
        self.current_history = 0
      self.current_path = path
      self.SetTitle(self.name + ' - ' + path)
      self.metadata.update(ls)

      # Tree: Traverse parent nodes, create them if they don't exist
      node = self.dir_tree.GetRootItem()
      if path != '' and path != '/':
        for d in path.split('/'):
          i, cookie = self.dir_tree.GetFirstChild(node)
          while True:
            if not i.IsOk():
              new = self.dir_tree.AppendItem(node, d)
              self.dir_tree.SetItemImage(new, self.ico_folder)
              self.dir_tree.SortChildren(node)
              node = new
              break
            if self.dir_tree.GetItemText(i) == d:
              node = i
              break
            i, cookie = self.dir_tree.GetNextChild(node, cookie)

      # Tree: Update child nodes for current directory
      dirs = []
      for p in ls:
        if 'SHA1' not in ls[p]:
          dirs.append(p.split('/')[-1])
      i, cookie = self.dir_tree.GetFirstChild(node)
      while True:
        if not i.IsOk():
          break
        txt = self.dir_tree.GetItemText(i)
        if txt in dirs:
          dirs.remove(txt)
        else:
          self.dir_tree.Delete(i)
        i, cookie = self.dir_tree.GetNextChild(node, cookie)
      for d in dirs:
        n = self.dir_tree.AppendItem(node, d)
        self.dir_tree.SetItemImage(n, self.ico_folder)
        self.dir_tree.SortChildren(node)
      self.dir_tree.Expand(node)

      # File List
      dirs, files = [], []
      for p in ls:
        if 'SHA1' in ls[p]:
          files.append(p.split('/')[-1])
        else:
          dirs.append(p.split('/')[-1])
      self.file_list.ClearAll()
      for d in sorted(dirs):
        item = self.file_list.Append([d])
        self.file_list.SetItemImage(item, self.icon_folder)
      for f in sorted(files):
        item = self.file_list.Append([f])
        if self.is_photo(f):
          self.file_list.SetItemImage(item, self.icon_photo)
        else:
          self.file_list.SetItemImage(item, self.icon_file)
    thread.start_new_thread(async, (self,))

  def up(self, evt=None):
    self.address_bar.SetValue('/'.join(self.current_path.split('/')[:-1]))
    self.go()

  def back(self, evt):
    if self.current_history == (len(self.history) - 1): return
    self.current_history += 1
    self.address_bar.SetValue(self.history[self.current_history])
    self.go(record_history=False)

  def forward(self, evt):
    if self.current_history == 0: return
    self.current_history -= 1
    self.address_bar.SetValue(self.history[self.current_history])
    self.go(record_history=False)

  def OnTreeClick(self, evt):
    root = self.dir_tree.GetRootItem()
    node = evt.GetItem()
    path = []
    while node != root:
      path = [self.dir_tree.GetItemText(node)] + path
      node = self.dir_tree.GetItemParent(node)
    path = '/'.join(path)
    self.address_bar.SetValue(path)
    self.go()

  def OnListClick(self, evt):
    path = self.current_path + '/' + evt.GetText()
    if path.startswith('/'): path = path[1:]
    if 'SHA1' not in self.metadata[path]:
      self.address_bar.SetValue(path)
      self.go()
    else:
      if self.is_photo(path):
        print 'Loading Picture: ' + path
        Photo_Viewer(self, -1, path)
      else:
        print 'Loading File: ' + path
        def async(path):
          p = self.download_or_get_from_cache(path)
          os.startfile(p)
        thread.start_new_thread(async, (path,))

  def OnRightClick(self, evt):
    def properties(evt):
      m = self.metadata[path]
      self.msgbox(0, (
                  'Path: ' + path + '\n' +
                  'Size: ' + human_readable_size(m['size']) + '\n' +
                  'Date Modified: ' + datetime.datetime.fromtimestamp(m['mtime']).strftime('%X %x') + '\n' +
                  'SHA1 Hash: ' + m['SHA1']
                  ))

    def cut(evt):
      self.clipboard = path
      print 'Marked ' + path + ' for cutting.'

    def upload(evt):
      self.crupdate_file_picker(dst=path)

    def new_folder(evt):
      self.new_folder(path=path)

    def delete(evt):
      c = self.yesnobox('Are you sure you want to delete ' + path + '?\n' +
                        'While this action can technically be undone, ' +
                        'reversing it can be difficult.')
      if not c: return
      c = self.yesnobox('Last chance: are you really sure?')
      if not c: return
      print 'Deleting ' + path + '...'
      def async(self, path):
        try: self.NAS.remove(path)
        except Exception as e: self.handle_NAS_Error(e)
        if self.current_path == path: return self.up()
        if '/'.join(path.split('/')[:-1]) == self.current_path:
          self.address_bar.SetValue(self.current_path)
          self.go()
      thread.start_new_thread(async, (self, path))

    def paste(evt):
      if self.clipboard is None:
        print 'Skipping paste: nothing to paste.'
      else:
        dst = path + '/' + self.clipboard.split('/')[-1]
        if dst.startswith('/'): dst = dst[1:]
        print 'Moving ' + self.clipboard + ' to ' + dst + '...'
        def async(self, src, dst):
          try: self.NAS.move_file(src, dst)
          except Exception as e: self.handle_NAS_Error(e)
          if (
              '/'.join(src.split('/')[:-1]) == self.current_path or
              '/'.join(dst.split('/')[:-1]) == self.current_path
             ):
            self.address_bar.SetValue(self.current_path)
            self.go()
        thread.start_new_thread(async, (self, self.clipboard, dst))
        self.clipboard = None

    def rename(evt):
      base_path = '/'.join(path.split('/')[:-1])
      old_name = path.split('/')[-1]
      new_name = self.text_entry('Rename',
                                 'Please enter a new name for the file.',
                                 default=old_name)
      if new_name == '': return
      if '/' in new_name: return self.msgbox(wx.ICON_ERROR, 'Invalid Name!')
      new_path = base_path + '/' + new_name
      if new_path.startswith('/'): new_path = new_path[1:]
      print 'Renaming ' + old_name + ' to ' + new_name + '...'
      def async(self, src, dst):
        try: self.NAS.move_file(src, dst)
        except Exception as e: self.handle_NAS_Error(e)
        self.address_bar.SetValue(self.current_path)
        self.go()
      thread.start_new_thread(async, (self, path, new_path))

    m = wx.Menu()
    if type(evt) == wx._core.ContextMenuEvent:
      path = self.current_path
      pos = self.panel.ScreenToClient(evt.GetPosition())
      ctrl = self.panel
    elif type(evt) == wx._controls.ListEvent:
      path = self.current_path + '/' + evt.GetItem().GetText()
      pos = evt.GetPoint()
      ctrl = self.file_list
      evt.Veto()
    elif type(evt) == wx._controls.TreeEvent:
      root, c, path = self.dir_tree.GetRootItem(), evt.GetItem(), []
      while c != root:
        path = [self.dir_tree.GetItemText(c)] + path
        c = self.dir_tree.GetItemParent(c)
      path = '/'.join(path)
      pos = evt.GetPoint()
      ctrl = self.dir_tree

    if path.startswith('/'): path = path[1:]
    if path in self.metadata and 'SHA1' in self.metadata[path]:
      mitem = m.Append(wx.ID_ANY, 'Cut')
      self.Bind(wx.EVT_MENU, cut, mitem)
      mitem = m.Append(wx.ID_ANY, 'Delete')
      self.Bind(wx.EVT_MENU, delete, mitem)
      mitem = m.Append(wx.ID_ANY, 'Rename')
      self.Bind(wx.EVT_MENU, rename, mitem)
      mitem = m.Append(wx.ID_ANY, 'Properties')
      self.Bind(wx.EVT_MENU, properties, mitem)
    else:
      mitem = m.Append(wx.ID_ANY, 'Upload')
      self.Bind(wx.EVT_MENU, upload, mitem)
      mitem = m.Append(wx.ID_ANY, 'New Folder')
      self.Bind(wx.EVT_MENU, new_folder, mitem)
      if path != '':
        mitem = m.Append(wx.ID_ANY, 'Delete')
        self.Bind(wx.EVT_MENU, delete, mitem)
      mitem = m.Append(wx.ID_ANY, 'Paste')
      self.Bind(wx.EVT_MENU, paste, mitem)
    ctrl.PopupMenu(m, pos)

  def OnDragOut(self, evt):
    selection = []
    c = -1
    while True:
      c = self.file_list.GetNextItem(c, wx.LIST_NEXT_ALL, wx.LIST_STATE_SELECTED)
      if c == -1: break
      path = self.current_path + '/' + self.file_list.GetItem(c).GetText()
      if path.startswith('/'): path = path[1:]
      if 'SHA1' in self.metadata[path]: selection.append(path)
    if len(selection) < 1: return
    dropSource = wx.DropSource( evt.GetEventObject() )
    data = wx.FileDataObject()
    for f in selection:
      data.AddFile(self.name + '://' + f)
    dropSource.SetData(data)
    result = dropSource.DoDragDrop(0)

    h = win32gui.GetForegroundWindow()
    s = win32com.client.Dispatch("Shell.Application")
    dst = None
    for w in s.Windows():
      if int(w.Hwnd) == h:
        dst = w.LocationURL
    if dst and dst.startswith('file:///'):
      dst = urllib.unquote(dst[8:])
      print 'Downloading ' + str(len(selection)) + ' file(s) to ' + dst + '...'
      def async(self, dst, files):
        for f in files:
          fname = f.split('/')[-1]
          src_p = self.download_or_get_from_cache(f)
          dst_p = os.path.join(dst, fname)
          if os.path.exists(dst_p):
            c = self.yesnobox('A local copy of ' + fname + ' already exists.\n' +
                              'Would you like to replace it?')
            if not c: continue
          shutil.copy(src_p, dst_p)
          os.utime(dst_p, (self.metadata[f]['mtime'], self.metadata[f]['mtime']))
      thread.start_new_thread(async, (self, dst, selection))

  def clear_cache(self, evt):
    if not os.path.exists(self.cache_dir):
      self.msgbox(0, 'The cache doesn\'t exist so there\'s nothing to clear!')
      return

    total_size = 0
    for root, dirs, files in os.walk(self.cache_dir):
        for f in files:
            total_size += os.path.getsize(os.path.join(root, f))
    c = self.yesnobox('The cache contains ' + human_readable_size(total_size) +
                      ' of data.\nWould you like to clear it?')
    if c:
      print 'Starting to clear cache...'
      shutil.rmtree(self.cache_dir)
      print 'Finished clearing cache!'

  def new_folder(self, evt=None, path=None):
    if evt:
      path = self.current_path

    name = self.text_entry('New Folder', 'Please enter a folder name.')
    if name == '': return
    if '/' in name: return self.msgbox(wx.ICON_ERROR, 'Invalid folder name!')
    path = path + '/' + name
    if path.startswith('/'): path = path[1:]
    print 'Creating directory: ' + path
    def async(self, path):
      try: self.NAS.create_dir(path)
      except Exception as ex: self.handle_NAS_Error(ex)
      self.address_bar.SetValue(path)
      self.go()
    thread.start_new_thread(async, (self,path))

  def crupdate_file_picker(self, evt=None, dst=None):
    if dst is None:
      dst = self.current_path
    d = wx.FileDialog(self, "Upload Files", "", "",
                            "Any File|*", wx.FD_OPEN | wx.FD_MULTIPLE | wx.FD_FILE_MUST_EXIST)
    if d.ShowModal() == wx.ID_CANCEL: return
    files = d.GetPaths()
    self.crupdate(files, dst)

  def crupdate(self, files, dst):
    print 'Uploading ' + str(len(files)) + ' file(s) to ' + dst + '...'
    def async(self, files, dst):
      try: ls = self.NAS.list_dir(dst)
      except Exception as e: self.handle_NAS_Error(e)
      for f in files:
        rpath = dst + '/' + os.path.basename(f)
        s = {'size': os.path.getsize(f), 'last_check':time.time()}
        def cb(progress):
          if (time.time()-s['last_check']) > 10:
            print (
                   'Uploading ' + rpath +
                   ('     %.3f%%     (' % (100.0*progress/s['size'])) +
                   human_readable_size(progress) + ' of ' +
                   human_readable_size(s['size']) + ')'
                  )
            s['last_check'] = time.time()
        if rpath in ls:
          c = self.yesnobox(rpath + ' already exists.\n' +
                            'This upload will be treated as an update ' +
                            'and the older version will be replaced.\n' +
                            'Is that okay?')
          if not c: continue
          try: self.NAS.update_file(f, rpath, callback=cb)
          except Exception as e: self.handle_NAS_Error(e)
        else:
          pass
          try: self.NAS.upload_file(f, rpath, callback=cb)
          except Exception as e: self.handle_NAS_Error(e)
      if dst == self.current_path:
        self.address_bar.SetValue(dst)
        self.go()
    thread.start_new_thread(async, (self, files, dst))

  def search(self, evt):
    print 'Loading metadata for search...'
    def async(self):
      try: md = self.NAS.metadata()
      except Exception as e: self.handle_NAS_Error(e)
      self.metadata = md['files']
    thread.start_new_thread(async, (self,))
    Search_Window(self, -1)

class CrupdateFileDropTarget(wx.FileDropTarget):
  def __init__(self, window):
    wx.FileDropTarget.__init__(self)
    self.window = window

  def OnDropFiles(self, x, y, filenames):
    local_files, nas_files = [], []
    proto_NAS = self.window.name + '://'
    for f in filenames:
      if f.startswith(proto_NAS):
        nas_files.append(f[len(proto_NAS):])
      elif os.path.isfile(f):
        local_files.append(f)
    self.window.crupdate(local_files, self.window.current_path)
    if len(nas_files) > 0: print 'Moving ' + str(len(nas_files)) + ' file(s)...'
    def async(self, files):
      for f in files:
        dst = self.current_path + '/' + f.split('/')[-1]
        if dst.startswith('/'): dst = dst[1:]
        if f == dst: continue
        try: self.NAS.move_file(f, dst)
        except Exception as e: self.handle_NAS_Error(e)
    thread.start_new_thread(async, (self.window, nas_files))

class Photo_Viewer(wx.Frame):
  def __init__(self, parent, id, photo_path):
    super(Photo_Viewer, self).__init__(parent, title = 'Photo Viewer - Loading...', size = (800,600))
    self.icon = wx.Icon('photo.ico', wx.BITMAP_TYPE_ICO)
    self.SetIcon(self.icon)
    self.parent = parent
    self.SetBackgroundColour(wx.BLACK)
    img = wx.EmptyImage(1920,1080)  # TODO: Change this so it doesn't need a magic number
    self.imgCtrl = wx.StaticBitmap(self, wx.ID_ANY,
                                  wx.BitmapFromImage(img))
    self.Centre()
    self.Show(True)

    self.photo_dir = '/'.join(photo_path.split('/')[:-1])
    self.photos = []
    for p in self.parent.metadata:
      if '/'.join(p.split('/')[:-1]) == self.photo_dir and self.parent.is_photo(p):
        self.photos.append(p)

    self.photos.sort()
    self.current_photo = self.photos.index(photo_path)
    self.cache_paths = {}
    thread.start_new_thread(self.load_photos, (self.photos,
                                           self.current_photo,
                                           self.cache_paths))
    self.cache_paths[photo_path] = self.parent.download_or_get_from_cache(photo_path)
    self.change_photo(photo_path)
    self.Bind(wx.EVT_SIZE, self.resize)
    self.Bind(wx.EVT_KEY_DOWN, self.onkey)

  def load_photos(self, photos, idx, cache_paths):
    try:
      for i in xrange(1, len(self.photos)):
        for k in [idx+i, idx-i]:
          try:
            p = self.photos[k]
            self.cache_paths[p] = self.parent.download_or_get_from_cache(p)
          except IndexError:
            pass
    except wx._core.PyDeadObjectError:
      pass

  def change_photo(self, photo):
    title = 'Photo Viewer - ' + photo.split('/')[-1]
    if photo not in self.cache_paths:
      title += ' (Still Loading...)'
      self.img = wx.EmptyImage(1,1)
    else:
      self.img = wx.Image(self.cache_paths[photo], wx.BITMAP_TYPE_ANY)
    self.resize()
    self.SetTitle(title)

  def resize(self, evt=None):
    x, y = self.GetSize()
    ix, iy = self.img.GetSize()
    ny = y
    nx = (ix*y)/iy
    if nx > x:
      nx = x
      ny = (iy*x)/ix
      self.imgCtrl.SetPosition(wx.Point(0,(y-ny)/2))
    else:
      self.imgCtrl.SetPosition(wx.Point((x-nx)/2,0))
    bmp = self.img.Scale(nx, ny).ConvertToBitmap()
    bmp.SetMaskColour(wx.BLACK)
    self.imgCtrl.SetBitmap(bmp)
    self.Refresh()

  def onkey(self, evt):
    keycode = evt.GetKeyCode()
    if keycode == wx.WXK_LEFT:
      self.current_photo -= 1
      if self.current_photo < 0:
        self.current_photo = len(self.photos) - 1
      self.change_photo(self.photos[self.current_photo])
    elif keycode == wx.WXK_RIGHT:
      self.current_photo += 1
      if self.current_photo > len(self.photos) - 1:
        self.current_photo = 0
      self.change_photo(self.photos[self.current_photo])

class Search_Window(wx.Frame):
  def __init__(self, parent, id):
    super(Search_Window, self).__init__(parent, title = 'Search', size=(800,700))
    ico_find = wx.ArtProvider_GetIcon(wx.ART_FIND, wx.ART_FRAME_ICON, (48,48))
    self.SetIcon(ico_find)
    self.parent = parent
    self.SetBackgroundColour(wx.WHITE)
    panel = wx.Panel(self)
    sizer = wx.BoxSizer(wx.VERTICAL)

    search_sizer = wx.BoxSizer(wx.HORIZONTAL)
    self.search_bar = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER)
    self.search_bar.Bind(wx.EVT_TEXT_ENTER, self.search)
    search_sizer.Add(self.search_bar, proportion=1, flag=wx.EXPAND|wx.ALL, border=5)
    button_search = wx.Button(panel, label = 'Search', style = wx.BU_EXACTFIT)
    button_search.Bind(wx.EVT_BUTTON, self.search)
    search_sizer.Add(button_search, flag=wx.ALL, border=5)

    help_txt = (
                'Type a list of keywords separated by spaces. All results containing the keywords will be returned (case-insensitive).\n' +
                'Any phrases in quotes will be matched exactly (case-sensitive).\n\n' +
                'The following search operators can also be used:\n' +
                '  - maxdate: The maximum date modified\n' +
                '  - mindate: The minimum date modified\n' +
                '  - maxsize: The maximum size\n' +
                '  - minsize: The minimum size\n' +
                '  - endswith: Something that the filename ends with, usually an extension\n\n' +
                'The following is an example search query that uses everything:\n'
                'report "Final Draft" maxdate:10/1/2015 mindate:2/7/2014 maxsize:10MB minsize:10KB endswith:.doc\n'
               )
    txtctrl = wx.StaticText(panel, label=help_txt)

    self.results = wx.TextCtrl(panel, -1, style=wx.TE_MULTILINE|wx.TE_READONLY, size=(60,60))
    self.results.SetValue('Search results will appear here.')

    sizer.Add(search_sizer, flag = wx.EXPAND)
    sizer.Add(txtctrl, flag = wx.EXPAND | wx.ALL, border=15)
    sizer.Add(self.results, flag = wx.EXPAND, proportion=1)

    panel.SetSizerAndFit(sizer)
    self.Show(True)

  def parse_size(self, size):
    size = size.lower()
    if size.endswith('gb'):
      return (1024**3)*int(size[:-2])
    if size.endswith('mb'):
      return (1024**2)*int(size[:-2])
    if size.endswith('kb'):
      return (1024)*int(size[:-2])
    if size.endswith('b'):
      return int(size[:-1])
    return int(size)

  def parse_query(self, q):
    query, in_quote, quote = [], False, []
    for token in q.split(' '):
      if in_quote and token.endswith('"'):
        quote.append(token[:-1])
        query.append(('quote',' '.join(quote)))
        in_quote = False
        quote = []
      elif not in_quote and token.startswith('"'):
        in_quote = True
        quote.append(token[1:])
      elif in_quote:
        quote.append(token)
      elif token.startswith('maxdate:'):
        s = token[8:]
        t = time.mktime(datetime.datetime.strptime(s, "%m/%d/%Y").timetuple())
        query.append(('maxdate', t))
      elif token.startswith('mindate:'):
        s = token[8:]
        t = time.mktime(datetime.datetime.strptime(s, "%m/%d/%Y").timetuple())
        query.append(('mindate', t))
      elif token.startswith('maxsize:'):
        query.append(('maxsize', self.parse_size(token[8:])))
      elif token.startswith('minsize:'):
        query.append(('minsize', self.parse_size(token[8:])))
      elif token.startswith('endswith:'):
        query.append(('endswith', token[9:].lower()))
      else:
        query.append(('keyword', token.lower()))
    return query

  def file_matches_query(self, file, query):
    for t in query:
      if t[0] == 'keyword' and t[1] not in file.lower(): return False
      if t[0] == 'quote' and t[1] not in file: return False
      try:
        if t[0] == 'maxdate' and self.parent.metadata[file]['mtime'] > t[1]: return False
        if t[0] == 'mindate' and self.parent.metadata[file]['mtime'] < t[1]: return False
        if t[0] == 'maxsize' and self.parent.metadata[file]['size'] > t[1]: return False
        if t[0] == 'minsize' and self.parent.metadata[file]['size'] < t[1]: return False
      except KeyError: return False
      if t[0] == 'endswith' and not file.lower().endswith(t[1]): return False
    return True

  def search(self, evt):
    q = self.search_bar.GetValue()
    self.results.SetValue('')
    self.results.WriteText('Searching for ' + q + '...\n\n')
    try:
      query = self.parse_query(q)
    except:
      self.parent.msgbox(wx.ICON_ERROR, 'Invalid search query.\n' +
                                        'Please check for typos and try again.')
      self.results.SetValue('')
      return

    results = []
    for f in self.parent.metadata:
      if self.file_matches_query(f, query):
        results.append(f)
    self.results.WriteText('\n'.join(sorted(results)))
    if len(results) < 1:
      self.results.WriteText('No results found!')


with open('config.json', 'r') as f:
  config = json.loads(f.read())
NAS = libnas.NAS(config['Server_URL'], config['Password'], config['Cert_Path'])
app = wx.App()
Main_Window(None, -1, 'EasiNAS', NAS)
app.MainLoop()
