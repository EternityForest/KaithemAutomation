from common import fail,suceed

import persistancefiles


p = persistancefiles.TestHook()

p.write("some/place","test")

if not p.get("some/place") == "test":
    fail('')

p.append("some/place","test2")

if not p.get("some/place",index = 1) == "test2":
    fail('')

if not p.ls("some") == ['place']:
    fail('Added key to something but it did not show in the directory listing')
    
p.remove("some")

if not p.whatis("some/place") == None:
    fail(p.whatis("some/place"))


print("sucess in testing persistance files")