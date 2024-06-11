#pragma once

#include "inc_libCzi.h"
#include <iostream>

/// Class used to gather Bitmap image informations.
/// PImage will be exposed to python via Pyind11 through the buffer_protocol()
class PImage {

private:
	
	std::shared_ptr<libCZI::IBitmapData>	ptrBitmapData;	///< The pointer to the IBitMapData object.
	void*									ptrData;		///< The pointer to the first (top-left) pixel of the bitmap.
	std::size_t								stride;			///< The stride of the bitmap data (pointed to by `ptrData`).
	std::size_t GetNChannels()              const;          ///< The no. of channels of the bitmap data.

public:

	/// Constructor which constructs a PImage object from the given IBitmapData.
	/// bitMap->lock() will be called here to access to the data ptr.
	PImage(std::shared_ptr<libCZI::IBitmapData> bitMap);

	/// Destructor. It's defined to do the Unlock() Call.
	~PImage();
	
	std::size_t get_height() const { return this->ptrBitmapData->GetHeight(); }

	std::size_t get_width() const { return this->ptrBitmapData->GetWidth(); }

	/// Returns the number of dimensions of the BitmapData
	/// For now should always be 3
	std::uint8_t get_ndim() const { return 3; }

	/// Returns ptrData
	void* get_data() const { return this->ptrData; }
	
	/// Returns libCZI pixelType of bitmapData
	libCZI::PixelType get_pixelType() const { return this->ptrBitmapData->GetPixelType();}

	/// Returns size of a bitMap element (in Bytes) 
	std::size_t get_itemsize() const;

	/// Returns shape of the array
	std::vector<size_t> get_shape() const { return {get_height(), get_width(), GetNChannels()}; }

	/// Returns stride of the bitmap data (in Bytes)
	std::size_t get_stride() const { return this->stride; }

};