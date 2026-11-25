# STATE — Bridge Audit Registry

## QUEUE

<!-- attack-surface score = tvl×age×custom×chain; addrs from config/bridge_allowlist.json (not DefiLlama address) -->

| # | name | chain | addr | tvl | score | stage |
|---|------|-------|------|-----|-------|-------|
| 1 | Across SpokePool | base | 0x09aea4b2242abc8bb4bb78d537a67a245a7bec64 | $11,732,403 | 12 | NEW |
| 2 | Across SpokePool | ethereum | 0x5c7bcd6e7de5423a257d81b442095a1a6ced35c5 | $11,732,403 | 6 | SAFE |
| 3 | Allbridge Core | ethereum | 0xb753548f6e010e7e680ba186f9ca1bdab2e90cf2 | manual | 6 | NEW |
| 4 | Celer cBridge | ethereum | 0x5427fefa711eff984124bfbb1ab6fbf5e3da1820 | $10,365,496 | 6 | NEW |
| 5 | Chainlink CCIP Router | ethereum | 0x80226fc0ee2b096224eeac085bb9a8cba1146f7d | $1,686,916,258 | 6 | NEW |
| 6 | Connext Diamond | ethereum | 0x8898b472c54c31894e3b9bb83cea802a5d0e63c6 | $17,591 | 6 | NEW |
| 7 | deBridge Gate | ethereum | 0x43de2d77bf8027e25dbd179b491e8d64f38398aa | $1,371,743 | 6 | NEW |
| 8 | Hop L1 Bridge | ethereum | 0xb8901acb165ed027e32754e0ffe830802919727f | $2,924,880 | 6 | NEW |
| 9 | Ink L1 Standard Bridge | ink | 0x4200000000000000000000000000000000000010 | $37,444,248 | 6 | NEW |
| 10 | Robinhood L1 ERC20 Gateway | robinhood | 0x1e324b9316138ca9a73f960213621ad1aaf01b89 | manual | 6 | NEW |
| 11 | Synapse Bridge | ethereum | 0x2796317b0ff8538f253012862c06787adfb8ceb6 | manual | 6 | NEW |
| 12 | Stargate V2 Pool | bsc | 0x4a364f8c717caad9a442737eb7b8a55cc6cf18d8 | $73,492,672 | 4 | NEW |
| 13 | Ink L1 Standard Bridge | ethereum | 0x88ff1e5b602916615391f55854588efcbb7663f0 | $37,444,248 | 3 | NEW |
| 14 | Linea L1 Message Service | ethereum | 0xd19d4b5d358258f05d7b411e21a1460d11b0876f | $42,469,884 | 3 | NEW |
| 15 | Robinhood L1 ERC20 Gateway | ethereum | 0x85001cc4867c5e1c22da4b79bb8852b9e2a06da0 | manual | 3 | NEW |
| 16 | zkSync Era Diamond | ethereum | 0x32400084c286cf3e17e7b677ea9583e60a000324 | manual | 3 | NEW |
| 17 | Stargate V2 Pool | arbitrum | 0xa45b5130f36cdca45667738e2a258ab09f4a5f7f | $73,492,672 | 2 | SAFE |
| 18 | Polygon PoS RootChainManager | ethereum | 0xa0c68c638235ee32657e8f720a23cec1bfc77c77 | $2,140,246,998 | 1 | NEW |
| 19 | Wormhole TokenBridge | ethereum | 0x3ee18b2214aff97000d974cf647e7c347e8fa585 | $1,075,467,648 | 1 | SAFE |

## CURSOR

current: #1

## EXCLUDED

| name | chain | addr | date | note |
|------|-------|------|------|------|
| LayerZero V2 | ethereum | 0x6985884c4392d348587b19cb9eaaf157f13271cd | 2026-11-25 | wrong contract (token ZRO) |
| Arbitrum Bridge | arbitrum | 0x912ce59144191c1204e64559fe8253a0e49e6548 | 2026-11-25 | wrong contract (token ARB) |
| Polygon Bridge | ethereum | 0x455e53cbb86018ac2b8092fdcd39d8444affc3f6 | 2026-11-25 | wrong contract (token POL) |
| Lighter Bridge | ethereum | 0x232ce3bd40fcd6f80f3d55a522d03f25df784ee2 | 2026-11-25 | wrong contract (token LIT) |
| Lorenzo enzoBTC | bsc | 0x3aee7602b612de36088f3ffed8c8f10e86ebf2bf | 2026-11-25 | wrong contract (token BANK) |
| SolvBTC | ethereum | 0x256f2d67e52fe834726d2ddcd8413654f5eb8b53 | 2026-11-25 | wrong contract (token SOLV) |
| Mantle Bridge | ethereum | 0x3c3a81e81dc49a522a592e7622a7e711c06bf354 | 2026-11-25 | wrong contract (token MNT) |
| xDAI Stake Bridge | ethereum | 0x0ae055097c6d159879521c384f1d2123d1f195e6 | 2026-11-25 | wrong contract (token STAKE) |
| Lombard BTC.b | ethereum | 0xf0db65d17e30a966c2ae6a21f6bba71cea6e9754 | 2026-11-25 | wrong contract (token BARD) |
| Axelar | ethereum | 0x467719ad09025fcc6cf6f8311755809d45a5e5f3 | 2026-11-25 | wrong contract (token AXL) |
| Portal | ethereum | 0x3ee18b2214aff97000d974cf647e7c347e8fa585 | 2026-11-25 | SAFE (AC ok, no admin, Wormhole Governor) |
| Hyperlane | arbitrum | 0xc9d23ed2adb0f551369946bd377f8644ce1ca5c4 | 2026-11-25 | wrong contract (no-bridge-surface) |
| edgeX Bridge | ethereum | 0xb0076de78dc50581770bba1d211ddc0ad4f2a241 | 2026-11-25 | wrong contract (no-bridge-surface) |
| B2 Buzz | bsc | 0x783c3f003f172c6ac5ac700218a357d2d66ee2a2 | 2026-11-25 | wrong contract (no-bridge-surface) |
| Starknet Bridge | ethereum | 0xca14007eff0db1f8135f4c25b34de49ab0d42766 | 2026-11-25 | wrong contract (no-bridge-surface) |
| Grvt Bridge | ethereum | 0xad29f2723fcdbcf665f210f25e06f97477e417cf | 2026-11-25 | wrong contract (no-bridge-surface) |
| Multichain | ethereum | 0x9fb9a33956351cf4fa040f65a13b835a3c8764e3 | 2026-11-25 | wrong contract (no-bridge-surface) |
| PumpBTC | bsc | 0xb7c0007ab75350c582d5eab1862b872b5cf53f0c | 2026-11-25 | wrong contract (no-bridge-surface) |
| Paradex Bridge | ethereum | 0xb32e10022ffbedfe10bc818a1c7e67d9d87e0fa7 | 2026-11-25 | wrong contract (no-bridge-surface) |
| Orderly Bridge | ethereum | 0xabd4c63d2616a5201454168269031355f4764337 | 2026-11-25 | wrong contract (no-bridge-surface) |
| Cronos zkEVM Bridge | ethereum | 0x28ff2e4dd1b58efeb0fc138602a28d5ae81e44e2 | 2026-11-25 | wrong contract (no-bridge-surface) |
| Across | ethereum | 0x44108f0223a3c3028f5fe7aec7f9bb2e66bef82f | 2026-11-25 | wrong contract (no-bridge-surface) |
| cBridge | ethereum | 0x4f9254c83eb525f9fcf346490bbb3ed28a81c667 | 2026-11-25 | wrong contract (no-bridge-surface) |
| Symbiosis | ethereum | 0xd38bb40815d2b0c2d2c866e0c72c5728ffc76dd9 | 2026-11-25 | wrong contract (no-bridge-surface) |
| Synapse Cross Chain Bridge | ethereum | 0x0f2d719407fdbeff09d87557abb7232601fd9f29 | 2026-11-25 | wrong contract (no-bridge-surface) |
| Metis Bridge | ethereum | 0x9e32b13ce7f2e80a01932b42553652e053d6ed8e | 2026-11-25 | wrong contract (no-bridge-surface) |
| APX Bridge | bsc | 0x000ae314e2a2172a039b26378814c252734f556a | 2026-11-25 | wrong contract (no-bridge-surface) |
| Injective Bridge | ethereum | 0xe28b3b32b6c345a34ff64674606124dd5aceca30 | 2026-11-25 | wrong contract (no-bridge-surface) |
| Eclipse Bridge | ethereum | 0x6055dc6ff1077eebe5e6d2ba1a1f53d7ef8430de | 2026-11-25 | wrong contract (no-bridge-surface) |
| Zora Bridge | base | 0x1111111111166b7fe7bd91427724b487980afc69 | 2026-11-25 | wrong contract (no-bridge-surface) |
| Zircuit | ethereum | 0xfd418e42783382e86ae91e445406600ba144d162 | 2026-11-25 | wrong contract (no-bridge-surface) |
| Hop Protocol | ethereum | 0xc5102fe9359fd9a28f877a67e36b0f050d81a3cc | 2026-11-25 | wrong contract (no-bridge-surface) |
| Taiko Bridge | ethereum | 0x10dea67478c5f8c5e2d90e5e9b26dbe60c54d800 | 2026-11-25 | wrong contract (no-bridge-surface) |
| BOB Bridge | ethereum | 0xc9746f73cc33a36c2cd55b8aefd732586946cedd | 2026-11-25 | wrong contract (no-bridge-surface) |
| hemiBTC | ethereum | 0xeb964a1a6fab73b8c72a0d15c7337fa4804f484d | 2026-11-25 | wrong contract (no-bridge-surface) |
| Lisk Bridge | ethereum | 0x6033f7f88332b8db6ad452b7c6d5bb643990ae3f | 2026-11-25 | wrong contract (no-bridge-surface) |
| SoDEX Bridge | ethereum | 0x624e2e7fdc8903165f64891672267ab0fcb98831 | 2026-11-25 | wrong contract (no-bridge-surface) |
| Orbit Bridge | ethereum | 0x662b67d00a13faf93254714dd601f5ed49ef2f51 | 2026-11-25 | wrong contract (no-bridge-surface) |
| Stargate V2 | arbitrum | 0xa45b5130f36cdca45667738e2a258ab09f4a5f7f | 2026-11-25 | SAFE (endpoint+OFT, mint from 0x0=false) |

## FINDINGS

<!-- append-only: date | name | chain | addr | class | link -->
