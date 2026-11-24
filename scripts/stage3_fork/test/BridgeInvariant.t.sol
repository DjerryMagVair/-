// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {MockBridge} from "../src/MockBridge.sol";
import {IBridgeViews} from "../src/IBridgeViews.sol";

/// @title Invariant regression template for bridge audit STAGE 3
/// @notice Asserts *secure* behaviour. A failing assertion on a live fork
///         is an audit signal for the analyst — not an exploit payload.
contract BridgeInvariantTest is Test {
    MockBridge internal mock;
    address internal attacker = address(0xBEEF);
    address internal ownerAddr;

    /// @dev Optional live target via BRIDGE_ADDR (fork mode). Empty = mock only.
    address internal live;

    function setUp() public {
        mock = new MockBridge();
        ownerAddr = mock.owner();
        // Fund locked collateral so owner mint within cap is valid.
        vm.deal(address(this), 100 ether);
        mock.lock{value: 10 ether}();

        string memory envAddr = vm.envOr("BRIDGE_ADDR", string(""));
        if (bytes(envAddr).length == 42) {
            live = vm.parseAddress(envAddr);
        }
    }

    // -------- Mock template (acceptance: forge test passes) --------

    function test_invariant_totalMinted_le_totalLocked() public view {
        assertLe(mock.totalMinted(), mock.totalLocked(), "unbacked mint invariant");
    }

    function test_mint_from_unauthorized_reverts() public {
        vm.prank(attacker);
        vm.expectRevert(MockBridge.NotOwner.selector);
        mock.mint(attacker, 1);
        // invariant still holds after denied call
        assertLe(mock.totalMinted(), mock.totalLocked());
    }

    function test_owner_cannot_mint_beyond_locked() public {
        uint256 room = mock.totalLocked() - mock.totalMinted();
        vm.prank(ownerAddr);
        vm.expectRevert(MockBridge.UnbackedMint.selector);
        mock.mint(ownerAddr, room + 1);
        assertLe(mock.totalMinted(), mock.totalLocked());
    }

    function test_owner_mint_within_cap_preserves_invariant() public {
        vm.prank(ownerAddr);
        mock.mint(ownerAddr, 1 ether);
        assertLe(mock.totalMinted(), mock.totalLocked());
    }

    // -------- Live fork hooks (skip if BRIDGE_ADDR unset) --------

    modifier whenLive() {
        vm.skip(live == address(0));
        _;
    }

    function testFork_invariant_totalMinted_le_totalLocked() public whenLive {
        // Best-effort: call common view selectors; skip if missing.
        try IBridgeViews(live).totalMinted() returns (uint256 minted) {
            try IBridgeViews(live).totalLocked() returns (uint256 locked) {
                assertLe(minted, locked, "LIVE: totalMinted > totalLocked");
            } catch {
                vm.skip(true);
            }
        } catch {
            vm.skip(true);
        }
    }

    function testFork_unauthorized_mint_must_revert() public whenLive {
        vm.prank(attacker);
        (bool ok,) = live.call(
            abi.encodeWithSignature("mint(address,uint256)", attacker, uint256(1))
        );
        // Secure behaviour: call fails. If it succeeds → invariant regression signal.
        assertFalse(ok, "LIVE: mint callable by unauthorized account");
    }
}
