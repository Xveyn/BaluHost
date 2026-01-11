#include <gtest/gtest.h>
#include <filesystem>
#include <fstream>
#include "sync/change_detector.h"

using namespace baludesk;
namespace fs = std::filesystem;

TEST(ChangeDetectorHashTest, ComputesSHA256ForFile) {
    // Create temp directory
    auto tmp = fs::temp_directory_path() / "cd_hash_test_dir";
    fs::create_directories(tmp);

    auto filePath = tmp / "test.txt";
    // Write known content "abc" (no newline)
    std::ofstream ofs(filePath.string(), std::ios::binary);
    ofs << "abc";
    ofs.close();

    // Instantiate ChangeDetector with null db/http (we guarded for null)
    ChangeDetector detector(nullptr, nullptr);

    // Run local scan; since DB is null, file will be reported as CREATED
    auto changes = detector.detectLocalChanges("folder1", tmp.string());

    ASSERT_FALSE(changes.empty());
    auto found = std::find_if(changes.begin(), changes.end(), [&](const DetectedChange& c) {
        return c.path == std::string("test.txt");
    });
    ASSERT_NE(found, changes.end());
    ASSERT_TRUE(found->hash.has_value());

    // SHA256("abc") expected
    const std::string expected = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad";
    EXPECT_EQ(found->hash.value(), expected);

    // Cleanup
    fs::remove(filePath);
    fs::remove(tmp);
}
