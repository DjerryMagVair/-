// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @notice Minimal view / access surface used by invariant regression tests.
interface IBridgeViews {
    function totalMinted() external view returns (uint256);
    function totalLocked() external view returns (uint256);
    function mint(address to, uint256 amount) external;
    function owner() external view returns (address);
}
