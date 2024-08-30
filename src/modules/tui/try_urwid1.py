import urwid as u

t = u.Text(u"Hello World")
f = u.Filler(t, 'top')
loop = u.MainLoop(f)
loop.screen.set_mouse_tracking()
loop.run()
