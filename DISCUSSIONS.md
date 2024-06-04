# This page contains information about discussions and ideas about future improvements to the library.


## High-Level API

### Read API

We want to represent CZI pixel data as n-dimensional numpy.arrays, which is the standard way of dealing with data in python, particularly in the context of Machine Learning (that spawned the development of pylibCZIrw).

Current Idea:

**`reader = czi.get_reader(dimensions, scene_index, pixel_type)`**

###### dimensions
This is a string that states what dimensions we want to access. This is necessary for mapping the array axes to a plane coordinate.
Important: The dimensions string needs to match the exact dimensions of the CZI otherwise, the call will throw.

###### scene_index (optional)
Same as in the low-level API
Including the scenes in the dimensions string and thus the array syntax, we'd run into some of the issues described in the [handling scenes](/technical_info.md) section.

###### pixel_type (optional)
Same as in the low-level API

###### reader
The reader is essentially a lazy-loading array with the shape of the accessed scene.

##### Reading the data

We can then use the standard array-reading syntax on the reader to read the CZI data.
Example:

**`data = reader[1:4, :, :]`**

Internally, this syntax produces a cascade of [low-level](#low-level-api-1st-development-stage) read calls whose resulting bitmaps are composed into the returned n-dimensional array. This is illustrated in below:

![nd-array](/doc/images/nd_array.png)

### Write API

We want to be able to write a n-dimensional array to a CZI in a way consistent with the read syntax:

Ideas:

**`writer = czi.get_writer(dimensions, scene_index, pixel_type)`**
**`writer.write(data)`**

## Writing multiple subblocks

We want to allow writing large data into a plane without having to break it down.
To achieve it we want to have a C++ call that can take a big bitmap, breaks it down into multiple subblocks before writing them.

When breaking down the data array into subblocks the following rules must be followed:
1. There should not be pathologically small subblocks, i.e. subblocks that are much smaller than their counterparts. So when "tiling" the array, one must aim for subblocks of roughly the same size.
2. The width or height of a subblock should not be larger than around 8k (or maybe 16k at max).
3. Do not use the ReplaceSubBlock call. This call appends subblocks and updates the indices but does not remove the replaced subblock. This can bloat the file so we'll not do it.
4. 1 superseeds 2.

##### Tiling strategy

<span style="color:	#FF8C00">To be defined.</span>
- Tiling should be independent of pixel type, so please don’t take sizeof(pixel) into account when calculating tile sizes
- We need to set M indices on the subblocks. We need to cache the last M index so that the next write writes the next M. m index is per scene and per plane.
- Skip writing subblock metadata for now. If it becomes an issue, revisit.

