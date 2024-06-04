#include "site.h"
#include "inc_libCzi.h"
#include "StaticContext.h"

void OneTimeSiteInitialization()
{
#ifdef _WIN32
	// In a Windows-environment, we can safely use the JPGXR-WIC-codec - which might be
	//  faster than the embedded JPGXR-decoder that comes with libCZI (although I never
	//  benchmarked it...).
	//  This site-object must be set before any calls to libCZI are made.
	libCZI::SetSiteObject(libCZI::GetDefaultSiteObject(libCZI::SiteObjectType::WithWICDecoder));
#endif

	libCZI::StreamsFactory::Initialize();

	kStaticContext.Initialize();
}
