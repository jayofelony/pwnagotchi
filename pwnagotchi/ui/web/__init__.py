import os
import time
from threading import Lock

# pwny-hydra - need separate files for multiple processes
frame_path = '/var/tmp/pwnagotchi/pwnagotchi%d.png' % os.getpid()
frame_format = 'PNG'
frame_ctype = 'image/png'
frame_lock = Lock()

# clean up old files
imdir = "/var/tmp/pwnagotchi"
now = time.time()
for file in os.listdir(imdir):
    if file.startswith("pwnagotchi") and file.endswith("png"):
        filename = os.path.join(imdir, file)
        st = os.stat(filename)
        if now - st.st_mtime > 3600:        
            os.remove(filename)

def update_frame(img):
    global frame_lock, frame_path, frame_format
    if not os.path.exists(os.path.dirname(frame_path)):
        os.makedirs(os.path.dirname(frame_path))
    with frame_lock:
        img.save(frame_path, format=frame_format)
