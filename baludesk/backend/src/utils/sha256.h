/* Small SHA256 helper (public-domain style implementation) */
#pragma once

#include <string>

namespace baludesk {

// Compute SHA256 of file contents and return hex string (lowercase)
std::string sha256_file(const std::string& filePath);

} // namespace baludesk
