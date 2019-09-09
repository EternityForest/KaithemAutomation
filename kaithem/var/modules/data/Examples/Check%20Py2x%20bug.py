## Code outside the data string, and the setup and action blocks is ignored
## If manually editing, you must reload the code through the web UI
__data__="""
{continual: false, disabled: false, once: true, priority: interactive, rate-limit: 0.0,
  resource-timestamp: 1566264981106420, resource-type: event}

"""

__trigger__='False'

if __name__=='__setup__':
    #This will cause two issues in python 2, a dictionary changed size suring iteration bug, and an error wherin it won't be able to find p
    p=0

def eventAction():
    p+=1
    x={}
