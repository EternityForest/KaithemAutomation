import common
from kaithem.src import persistancefiles
p = persistancefiles.PersistanceFile("ass")
p.write("tavern1","Hell's End Tavern")
persistancefiles.saveAll()
