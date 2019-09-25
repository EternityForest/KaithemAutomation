# Filedata Storage

This folder contains the actual file contents of file resources. They are organized by module,
the path after that follows the resource name.

In external modules, files are stored in a `__filedata__`  folder, with the path after that following the resource path.


The metadata for the resources is stored in the modules themselves. 

## Deletion
Anything(AT ALL) in this folder
that does not correspond to a resource in a module MAY BE GARBAGE COLLECTED!!

THIS INCLUDES .git FOLDERS! 