import time
from time import time

from icemedia.iceflow import GstreamerPipeline

p = GstreamerPipeline()
p.add_element(
    "jackaudiosrc",
    blocksize=64,
    connect=1,
    buffer_time=1000,
)
# p.add_element("audiotestsrc", is_live=True)
p.add_element("audioconvert")
p.add_element(
    "jackaudiosink",
    buffer_time=1000,
    blocksize=64,
    connect=1,
    **{"async": True},
    slave_method=0,
)
p.start(timeout=2)
time.sleep(100)
print(p.getPosition())

p.stop()
