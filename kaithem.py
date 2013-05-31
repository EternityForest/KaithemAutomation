#This is the global general purpose utility thing
import time
import modules
import weekday


class Kaithem():
    def lorem(self):
        return ("""lorem ipsum dolor sit amet, consectetur adipiscing elit. Proin vitae laoreet eros. Integer nunc nisl, ultrices et commodo sit amet, dapibus vitae sem. Nam vel odio metus, ac cursus nulla. Pellentesque scelerisque consequat massa, non mollis dolor commodo ultrices. Vivamus sit amet sapien non metus fringilla pretium ut vitae lorem. Donec eu purus nulla, quis venenatis ipsum. Proin rhoncus laoreet ullamcorper. Etiam fringilla ligula ut erat feugiat et pulvinar velit fringilla.""")
   
    def hour(self):
        return(time.localtime().tm_hour)
    
    def minute(self):
        return(time.localtime().tm_min)
        
    def second(self):
        return(time.localtime().tm_sec)
    
    def dayofweek(self):
        return (weekday.DayOfWeek())
    
class obj():
    pass
        
kaithem = Kaithem()
kaithem.globals = obj() #this is just a place to stash stuff.
