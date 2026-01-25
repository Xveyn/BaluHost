#!/bin/bash
# BaluHost - mDNS Configuration Test Script
# Tests mDNS/Avahi configuration and hostname resolution

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
HOSTNAME="baluhost"
EXPECTED_HOSTNAME="${HOSTNAME}.local"
BACKEND_PORT=8000
FRONTEND_PORT=5173
WEBDAV_PORT=8080

# Test results
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_SKIPPED=0

# Helper functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_test() {
    echo -e "${BLUE}[TEST]${NC} $1"
}

log_pass() {
    echo -e "${GREEN}[PASS]${NC} $1"
    ((TESTS_PASSED++))
}

log_fail() {
    echo -e "${RED}[FAIL]${NC} $1"
    ((TESTS_FAILED++))
}

log_skip() {
    echo -e "${YELLOW}[SKIP]${NC} $1"
    ((TESTS_SKIPPED++))
}

# Divider
divider() {
    echo "=========================================="
}

# Test 1: Check if Avahi daemon is installed
test_avahi_installed() {
    log_test "Checking if Avahi is installed..."

    if command -v avahi-daemon &> /dev/null; then
        AVAHI_VERSION=$(avahi-daemon --version 2>&1 | head -n 1)
        log_pass "Avahi is installed: $AVAHI_VERSION"
        return 0
    else
        log_fail "Avahi is not installed"
        log_info "Install with: sudo apt install avahi-daemon avahi-utils"
        return 1
    fi
}

# Test 2: Check if Avahi daemon is running
test_avahi_running() {
    log_test "Checking if Avahi daemon is running..."

    if systemctl is-active --quiet avahi-daemon; then
        log_pass "Avahi daemon is running"
        return 0
    else
        log_fail "Avahi daemon is not running"
        log_info "Start with: sudo systemctl start avahi-daemon"
        return 1
    fi
}

# Test 3: Check Avahi configuration
test_avahi_config() {
    log_test "Checking Avahi configuration..."

    if [ ! -f /etc/avahi/avahi-daemon.conf ]; then
        log_fail "Avahi config file not found"
        return 1
    fi

    # Check if hostname is configured
    CONFIGURED_HOSTNAME=$(grep "^host-name=" /etc/avahi/avahi-daemon.conf 2>/dev/null | cut -d'=' -f2)

    if [ -n "$CONFIGURED_HOSTNAME" ]; then
        if [ "$CONFIGURED_HOSTNAME" = "$HOSTNAME" ]; then
            log_pass "Avahi configured with correct hostname: $CONFIGURED_HOSTNAME"
            return 0
        else
            log_warn "Avahi configured with different hostname: $CONFIGURED_HOSTNAME (expected: $HOSTNAME)"
            log_info "To fix: Edit /etc/avahi/avahi-daemon.conf and set host-name=$HOSTNAME"
            return 1
        fi
    else
        SYSTEM_HOSTNAME=$(hostname)
        log_warn "Avahi using system hostname: $SYSTEM_HOSTNAME"
        log_info "To use custom hostname: Edit /etc/avahi/avahi-daemon.conf and add: host-name=$HOSTNAME"
        return 1
    fi
}

# Test 4: Check if BaluHost service is published
test_avahi_service_published() {
    log_test "Checking if BaluHost service is published..."

    if ! command -v avahi-browse &> /dev/null; then
        log_skip "avahi-browse not available"
        return 0
    fi

    # Browse for BaluHost service (timeout after 5 seconds)
    SERVICES=$(timeout 5 avahi-browse -p -t _baluhost._tcp 2>/dev/null || true)

    if echo "$SERVICES" | grep -q "_baluhost._tcp"; then
        log_pass "BaluHost service is published via mDNS"
        # Show service details
        echo "$SERVICES" | grep "^=" | while read line; do
            echo "    $line"
        done
        return 0
    else
        log_fail "BaluHost service not found"
        log_info "Ensure BaluHost backend is running"
        return 1
    fi
}

# Test 5: Test hostname resolution
test_hostname_resolution() {
    log_test "Testing hostname resolution: $EXPECTED_HOSTNAME"

    if command -v avahi-resolve &> /dev/null; then
        # Try to resolve with avahi-resolve
        RESOLVED=$(avahi-resolve -n $EXPECTED_HOSTNAME 2>&1)

        if echo "$RESOLVED" | grep -q "Failed"; then
            log_fail "Cannot resolve $EXPECTED_HOSTNAME"
            log_info "Output: $RESOLVED"
            return 1
        else
            IP_ADDRESS=$(echo "$RESOLVED" | awk '{print $2}')
            log_pass "Resolved $EXPECTED_HOSTNAME → $IP_ADDRESS"
            return 0
        fi
    else
        log_skip "avahi-resolve not available"
        return 0
    fi
}

# Test 6: Test ping to hostname
test_ping_hostname() {
    log_test "Testing ping to $EXPECTED_HOSTNAME"

    # Try to ping (1 packet, 2 second timeout)
    if ping -c 1 -W 2 $EXPECTED_HOSTNAME &> /dev/null; then
        log_pass "Ping to $EXPECTED_HOSTNAME successful"
        return 0
    else
        log_fail "Ping to $EXPECTED_HOSTNAME failed"
        log_info "Ensure mDNS is working on this client"
        return 1
    fi
}

# Test 7: Check backend connectivity
test_backend_connectivity() {
    log_test "Testing backend API connectivity on port $BACKEND_PORT"

    # Get local IP
    LOCAL_IP=$(hostname -I | awk '{print $1}')

    # Try to connect to backend health endpoint
    if curl -s -o /dev/null -w "%{http_code}" --connect-timeout 2 "http://$LOCAL_IP:$BACKEND_PORT/api/health" 2>/dev/null | grep -q "200\|404"; then
        log_pass "Backend is reachable on port $BACKEND_PORT"
        return 0
    else
        log_warn "Backend not reachable on port $BACKEND_PORT (may not be running)"
        return 1
    fi
}

# Test 8: Check frontend connectivity
test_frontend_connectivity() {
    log_test "Testing frontend connectivity on port $FRONTEND_PORT"

    LOCAL_IP=$(hostname -I | awk '{print $1}')

    if curl -s -o /dev/null -w "%{http_code}" --connect-timeout 2 "http://$LOCAL_IP:$FRONTEND_PORT" 2>/dev/null | grep -q "200"; then
        log_pass "Frontend is reachable on port $FRONTEND_PORT"
        return 0
    else
        log_warn "Frontend not reachable on port $FRONTEND_PORT (may not be running)"
        return 1
    fi
}

# Test 9: Check WebDAV connectivity
test_webdav_connectivity() {
    log_test "Testing WebDAV connectivity on port $WEBDAV_PORT"

    LOCAL_IP=$(hostname -I | awk '{print $1}')

    if curl -s -o /dev/null -w "%{http_code}" --connect-timeout 2 "http://$LOCAL_IP:$WEBDAV_PORT/webdav" 2>/dev/null | grep -q "401\|200"; then
        log_pass "WebDAV is reachable on port $WEBDAV_PORT"
        return 0
    else
        log_warn "WebDAV not reachable on port $WEBDAV_PORT (may not be running)"
        return 1
    fi
}

# Test 10: Check firewall rules
test_firewall_mdns() {
    log_test "Checking firewall rules for mDNS (UDP 5353)"

    # Check if firewall is active
    if systemctl is-active --quiet ufw; then
        if sudo ufw status | grep -q "5353"; then
            log_pass "UFW allows mDNS traffic (port 5353)"
            return 0
        else
            log_warn "UFW may be blocking mDNS traffic"
            log_info "To fix: sudo ufw allow 5353/udp"
            return 1
        fi
    elif systemctl is-active --quiet firewalld; then
        if sudo firewall-cmd --list-services | grep -q "mdns"; then
            log_pass "Firewalld allows mDNS traffic"
            return 0
        else
            log_warn "Firewalld may be blocking mDNS traffic"
            log_info "To fix: sudo firewall-cmd --permanent --add-service=mdns && sudo firewall-cmd --reload"
            return 1
        fi
    else
        log_skip "No active firewall detected"
        return 0
    fi
}

# Test 11: Check NSS configuration (Linux only)
test_nss_mdns() {
    log_test "Checking NSS mDNS configuration"

    if [ ! -f /etc/nsswitch.conf ]; then
        log_skip "Not a standard Linux system"
        return 0
    fi

    HOSTS_LINE=$(grep "^hosts:" /etc/nsswitch.conf)

    if echo "$HOSTS_LINE" | grep -q "mdns"; then
        log_pass "NSS configured for mDNS: $HOSTS_LINE"
        return 0
    else
        log_warn "NSS may not be configured for mDNS"
        log_info "Current config: $HOSTS_LINE"
        log_info "Recommended: hosts: files mdns4_minimal [NOTFOUND=return] dns mdns4"
        return 1
    fi
}

# Test 12: Check BaluHost backend config
test_backend_config() {
    log_test "Checking BaluHost backend mDNS configuration"

    # Try to find .env file
    ENV_FILE=""
    for path in "../backend/.env" "./backend/.env" "./.env"; do
        if [ -f "$path" ]; then
            ENV_FILE="$path"
            break
        fi
    done

    if [ -z "$ENV_FILE" ]; then
        log_warn "Backend .env file not found"
        log_info "Create backend/.env with: MDNS_HOSTNAME=$HOSTNAME"
        return 1
    fi

    # Check if MDNS_HOSTNAME is set
    if grep -q "^MDNS_HOSTNAME=" "$ENV_FILE"; then
        MDNS_HOSTNAME=$(grep "^MDNS_HOSTNAME=" "$ENV_FILE" | cut -d'=' -f2)
        if [ "$MDNS_HOSTNAME" = "$HOSTNAME" ]; then
            log_pass "Backend configured with correct mDNS hostname: $MDNS_HOSTNAME"
            return 0
        else
            log_warn "Backend configured with different hostname: $MDNS_HOSTNAME (expected: $HOSTNAME)"
            return 1
        fi
    else
        log_warn "MDNS_HOSTNAME not set in $ENV_FILE"
        log_info "Add: MDNS_HOSTNAME=$HOSTNAME"
        return 1
    fi
}

# Summary report
show_summary() {
    divider
    echo ""
    log_info "Test Summary"
    divider
    echo ""
    echo -e "  ${GREEN}Passed:${NC}  $TESTS_PASSED"
    echo -e "  ${RED}Failed:${NC}  $TESTS_FAILED"
    echo -e "  ${YELLOW}Skipped:${NC} $TESTS_SKIPPED"
    echo ""

    if [ $TESTS_FAILED -eq 0 ]; then
        log_pass "All tests passed! ✅"
        echo ""
        log_info "BaluHost is accessible via:"
        echo "  - http://$EXPECTED_HOSTNAME"
        echo "  - http://$EXPECTED_HOSTNAME:$FRONTEND_PORT (Frontend)"
        echo "  - http://$EXPECTED_HOSTNAME:$BACKEND_PORT (Backend API)"
        echo "  - http://$EXPECTED_HOSTNAME:$WEBDAV_PORT/webdav (WebDAV)"
        echo ""
        return 0
    else
        log_error "Some tests failed. Review the output above for recommendations."
        echo ""
        log_info "Quick fixes:"
        echo "  - Install Avahi: sudo apt install avahi-daemon avahi-utils"
        echo "  - Configure hostname: sudo deploy/scripts/install-avahi.sh"
        echo "  - Start BaluHost: python start_dev.py"
        echo ""
        return 1
    fi
}

# Main test flow
main() {
    echo ""
    divider
    log_info "BaluHost mDNS Configuration Test"
    divider
    echo ""
    log_info "Testing hostname: $EXPECTED_HOSTNAME"
    echo ""

    # Run all tests (continue even if some fail)
    test_avahi_installed || true
    test_avahi_running || true
    test_avahi_config || true
    test_avahi_service_published || true
    test_hostname_resolution || true
    test_ping_hostname || true
    test_backend_connectivity || true
    test_frontend_connectivity || true
    test_webdav_connectivity || true
    test_firewall_mdns || true
    test_nss_mdns || true
    test_backend_config || true

    # Show summary
    echo ""
    show_summary
}

# Check if running with required permissions
if [ "$EUID" -eq 0 ]; then
    log_warn "Running as root. Some tests may behave differently."
fi

# Run tests
main

# Exit with appropriate code
if [ $TESTS_FAILED -eq 0 ]; then
    exit 0
else
    exit 1
fi
