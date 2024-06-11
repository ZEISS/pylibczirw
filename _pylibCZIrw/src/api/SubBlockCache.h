#pragma once
#include "inc_libCzi.h"

/// Enum to represent all available types of subblock caches
enum class CacheType : std::uint8_t {
  None = 0,
  Standard = 1 // Currently only one standard type of cache is supported
};

/// This POD ("plain-old-data") structure represents all options for configuring
/// a subblock cache
struct SubBlockCacheOptions {
  /// Cache only compressed subblocks
  bool cacheOnlyCompressed = true;

  /// The type of cache to be used
  CacheType cacheType = CacheType::None;

  libCZI::ISubBlockCache::PruneOptions pruneOptions;

  void Clear() {
    this->cacheOnlyCompressed = true;
    this->cacheType = CacheType::None;
    this->pruneOptions = libCZI::ISubBlockCache::PruneOptions();
  }
};

/// This POD ("plain-old-data") structure represents information on a subblock
/// cache.
struct SubBlockCacheInfo {
  std::uint32_t elementsCount =
      0; ///< Number of elements (subblocks) in the cache
  std::uint64_t memoryUsage = 0; ///< Memory usage of the cache in bytes
};