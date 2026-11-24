// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @dev Local mock that upholds audit invariants (for template acceptance).
contract MockBridge {
    address public owner;
    uint256 public totalMinted;
    uint256 public totalLocked;

    error NotOwner();
    error UnbackedMint();

    constructor() {
        owner = msg.sender;
    }

    function lock() external payable {
        totalLocked += msg.value;
    }

    function mint(address to, uint256 amount) external {
        if (msg.sender != owner) revert NotOwner();
        if (totalMinted + amount > totalLocked) revert UnbackedMint();
        totalMinted += amount;
        // accounting-only mock; no token transfer
        (to);
    }
}
