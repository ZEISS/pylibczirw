#pragma once
 
/// Perform some one-time initialization/configuration for the site (with libCZI). This includes
/// selecting the WIC-provided JPEGXR decoder as the default JPEG decoder
/// on the Windows platform, and setting up libcURL.
/// This should be called at "load time", before any other libCZI function is called.
void OneTimeSiteInitialization();
