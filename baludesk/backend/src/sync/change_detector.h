#pragma once

namespace baludesk {

// Forward declaration
class Database;

class ChangeDetector {
public:
    explicit ChangeDetector(Database* db);
    ~ChangeDetector();

private:
    Database* db_;
};

} // namespace baludesk
