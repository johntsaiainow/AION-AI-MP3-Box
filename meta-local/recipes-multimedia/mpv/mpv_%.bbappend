# AION MP3 Box: headless audio player
# Disable graphical display backends.

PACKAGECONFIG:remove = "lua wayland egl x11 opengl"
