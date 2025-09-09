

# **An Expert Report on DeFi Contract Addresses for EVM Transaction Classification**

## **1\. Executive Summary**

This report provides a comprehensive compendium of key smart contract addresses for seven prominent DeFi protocols: Uniswap, Aave, Balancer, Euler, Silo, Paraswap, and 1inch. The document is structured as an authoritative technical resource for a backend service classifying Ethereum Virtual Machine (EVM) transactions on the Ethereum mainnet. It details the architectural nuances of each protocol, differentiating between static, canonical contracts and dynamic, programmatically generated ones. The report identifies the primary entry-point contracts for core user actions such as swaps, liquidity provision, and lending, while also providing critical insights into transaction classification strategies and data integrity best practices.

A summary of key findings indicates that Uniswap and Balancer utilize distinct decentralized exchange (DEX) architectures: a factory-based model versus a vault-centric model. Uniswap V3's UniversalRouter serves as the modern entry point for swaps and liquidity management, superseding older routers.1 In contrast, Balancer V2/V3’s

Vault is a single, centralized contract that manages all asset accounting for its pools.2 Aave and Euler employ dynamic, upgradeable contract systems managed by a central registry. Aave's

PoolAddressesProvider is the recommended method for fetching live contract addresses, while Euler's addresses are maintained in a canonical GitHub repository known as euler-interfaces.4 Finally, 1inch and Paraswap function as DEX aggregators. Their primary transaction points are single router contracts (

Aggregation Router V6 for 1inch and Augustus Swapper for Paraswap). A crucial element for these protocols is that the transaction payload (callData) is generated off-chain by their respective APIs and simply executed on-chain by the router.8 Silo operates on a unique risk-isolated lending model where a

SiloFactory deploys new lending markets (Silo contracts) for each asset pair.10 This report concludes with actionable recommendations for building a resilient, accurate, and scalable backend service for DeFi applications.

## **2\. Foundational DeFi Architecture and Contract Patterns**

To build a robust backend service capable of accurately classifying DeFi transactions, it is essential to first understand the underlying smart contract architecture of each protocol. A simple list of addresses is insufficient, as the function and permanence of these addresses vary greatly. The following section lays the theoretical groundwork by outlining the primary architectural models used by the protocols in question. A proper transaction classification system must be designed with these models in mind to achieve a high match rate and long-term reliability.

### **2.1 The DEX Model: Automated Market Makers vs. Aggregators**

DeFi protocols can be broadly categorized based on their role in liquidity provision and trading. Automated Market Makers (AMMs) like Uniswap and Balancer are foundational DEXs where liquidity is held in smart contract pools. These pools use mathematical formulas to determine asset prices and execute trades. Conversely, DEX aggregators like 1inch and Paraswap do not hold their own liquidity. Instead, their contracts function as intelligent routers that find the most optimal trading paths across multiple underlying AMMs and other liquidity sources. The on-chain contract for an aggregator simply executes a complex series of instructions that were pre-calculated by an off-chain API.8 This distinction is fundamental to understanding how to interpret a transaction's on-chain footprint.

### **2.2 Key Architectural Patterns in DeFi**

The specific contract design patterns employed by protocols dictate the best approach for transaction classification. Recognizing these patterns is a necessary first step in building a resilient data service.

#### **The Factory Pattern**

This model is a cornerstone of decentralized, permissionless contract deployment. A single factory contract is deployed at a fixed, canonical address. Its sole purpose is to deploy new instances of a standardized contract, such as a liquidity pool, based on user-defined parameters. For example, Uniswap V2's factory is at 0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f on Ethereum mainnet.12 This factory is responsible for creating new

Pair contracts. A key feature of this model is the emission of an event, such as PairCreated, whenever a new contract is deployed. For a backend service, this event log is the most reliable way to discover and index new liquidity pools as they are created. Simply hardcoding a list of popular pairs is a temporary and incomplete solution; a durable service must listen for these events to maintain a comprehensive and up-to-date database of all active pools.12 Similarly, Uniswap V3 utilizes a factory contract at

0x1F98431c8aD98523631AE4a59f267346ea31F984 for deploying its concentrated liquidity pools.1 The factory pattern ensures that the system is permissionless and can grow without requiring a centralized entity to manage new deployments.

#### **The Vault-Centric Model**

This architecture, exemplified by Balancer, is a significant departure from the factory pattern. Instead of each pool holding its own assets, a single, central Vault contract is used to hold and manage all tokens for every pool in the protocol.2 Pool contracts in this model are simplified, containing only the mathematical logic for determining prices and executing swaps, but not the tokens themselves. All user interactions—swaps, adding liquidity, and removing liquidity—are routed through the single

Vault address. For a backend service, this presents a unique challenge for transaction classification. Since many different transactions will target the same Vault address, the simple to address is insufficient to determine the transaction's purpose. The real classification logic must reside in decoding the transaction's input data (callData) to identify the specific poolId and the exact action being performed.3 This design choice also has implications for efficiency, as it allows for gas-optimized "batch swaps" that minimize token transfers by netting out balances within the vault.3

#### **The Proxy and Registry Model**

This pattern is prevalent in protocols that require flexibility and upgradeability, such as lending protocols and governance systems. A single, immutable registry contract acts as a directory, holding the addresses of all other protocol components. These other components are often proxy contracts that delegate calls to an underlying, updatable implementation contract. The main registry, sometimes called a PoolAddressesProvider or similar, is the recommended entry point for fetching the most current addresses for a protocol's various components. For example, the Aave V3 documentation repeatedly states that the PoolAddressesProvider is the "main registry" and that developers should fetch the correct address from it before interacting with the protocol's core Pool contract.4 This is a crucial design choice that acts as a security measure, allowing governance to update contract implementations without changing the user-facing addresses. For a developer, this means that hardcoding addresses is an unsafe practice that will inevitably lead to a service failure if the protocol upgrades. The proper workflow is to dynamically query the registry contract to get the latest addresses for all other core contracts.

### **2.3 Deeper Implications of Architectural Choices**

The architectural patterns discussed above have profound implications for building a reliable DeFi data service. The evolution of protocols often leads to the adoption of more advanced patterns. For instance, the transition from older, action-specific contracts to a single, unified router is a notable trend. Both Uniswap V3's UniversalRouter and 1inch's Aggregation Router V6 serve as centralized entry points for a wide range of functions, including swaps, adding liquidity, and NFT operations.1 This design simplifies the initial address-based filtering for a transaction but shifts the burden of classification to the analysis of the transaction's

callData. A classification service must be able to parse these complex, encoded instructions to provide a granular breakdown of the user's actions.

Furthermore, protocols that rely on off-chain components, like DEX aggregators, introduce an additional layer of complexity. Paraswap's documentation states that the callData for a swap is provided by its API.8 This means the on-chain contract simply executes a pre-determined, optimized path. For a backend service, this indicates that a transaction to a Paraswap

Augustus Swapper contract is not a simple, single-pool interaction. To provide a truly detailed classification, the service would need to either replicate the complex pathfinding logic of the aggregator or integrate with its API to understand the trade's full itinerary. A simple label of "Paraswap Swap" is a starting point, but a more advanced feature would trace the individual swaps that the aggregator performed across various liquidity sources.

Finally, the choice between a distributed factory model and a centralized registry/vault model carries important security and operational considerations. The permissionless nature of Uniswap's factory system allows anyone to create new pools, leading to a sprawling and diverse ecosystem of contracts that must be continuously indexed. In contrast, Balancer's centralized Vault and Aave's PoolAddressesProvider provide single points of control and query, which can simplify a developer's workflow but also represent a single point of failure. A backend service must be built to handle these different paradigms, with a clear understanding that a hardcoded, static list of contracts is not a sustainable solution for a dynamic and evolving DeFi landscape.

## **3\. Protocol-Specific Contract Registry**

This section provides a detailed, protocol-by-protocol breakdown of the most important contract addresses for the Ethereum mainnet, their functions, and how they should be handled for transaction classification.

### **3.1 Uniswap: The Quintessential Automated Market Maker**

Uniswap is a seminal DEX that pioneered the AMM model. It exists in multiple versions, each with a distinct architecture that must be understood for accurate transaction classification.

#### **3.1.1 Uniswap V2 Contracts**

Uniswap V2 relies on the factory pattern. Its core is the UniswapV2Factory contract, deployed at 0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f on the Ethereum mainnet.12 This factory's primary function is to create new liquidity

Pair contracts. Each Pair is a unique, dynamic contract that holds liquidity for a specific token pair. To identify a transaction targeting a V2 pool, a backend service must first maintain an up-to-date list of all existing Pair contracts. A robust way to achieve this is by monitoring the PairCreated event emitted by the UniswapV2Factory contract. This event provides the addresses of the two tokens and the newly created Pair contract, allowing the service to automatically add new pools to its database.12 A secondary method for finding an existing pool's address is to call the

getPair(address tokenA, address tokenB) function on the factory contract itself.12

#### **3.1.2 Uniswap V3 Contracts**

Uniswap V3 introduced the concept of concentrated liquidity, where a user’s position is represented by an ERC-721 NFT. The main factory contract, UniswapV3Factory, is deployed at 0x1F98431c8aD98523631AE4a59f267346ea31F984.1 A critical component for user interaction is the

UniversalRouter at 0x66a9893cc07d91d95644aedd05d03f95e1dba8af.1 This contract is the modern, preferred entry point for swaps and liquidity management and has replaced older contracts like

SwapRouter02 (0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45).1 Transactions that interact with the

UniversalRouter must be classified by decoding the callData to understand the specific commands being executed. Liquidity management is handled by the NonfungiblePositionManager contract at 0xC36442b4a4522E871399CD717aBDD847Ab11FE88.1 A transaction targeting this address signifies the creation, update, or burning of a liquidity position NFT. Therefore, a classification system must be able to differentiate between direct swaps and liquidity management operations based on the target contract.

### **3.2 Aave: A Lending Protocol Driven by Proxies**

Aave's architecture is built on a proxy and registry model, which is crucial for its upgradeability and security. Hardcoding any address other than the registry is an anti-pattern and a potential security risk.

#### **3.2.1 Aave V3 Core Contracts**

The central and most important contract for Aave V3 is the PoolAddressesProvider. This contract is an immutable registry that stores the addresses of all other protocol components.4 The documentation explicitly recommends fetching the correct addresses from this contract whenever the

Pool contract or other components are needed.4 The user-facing

Pool contract, which handles all lending and borrowing actions, is managed by this provider. The PoolConfigurator is an administrative contract used for configuring the protocol's reserves and is also registered with the PoolAddressesProvider.5

To build a reliable classification service, the backend must implement a dynamic address fetching mechanism. At startup or at regular intervals, the service should query the PoolAddressesProvider to get the latest addresses for the core Pool contract and other relevant components. A transaction targeting the Pool contract can be classified by decoding its function selector to determine if it is a supply, borrow, repay, or withdraw operation.14 This dynamic approach ensures that the service remains operational even after governance-driven contract upgrades.

**Table 1: Key Uniswap and Aave Ethereum Mainnet Contracts**

| Protocol | Contract Name | Address | Notes on Function/Role | Dynamic Discovery Method |
| :---- | :---- | :---- | :---- | :---- |
| Uniswap V2 | UniswapV2Factory | 0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f | Deploys new V2 liquidity pairs. | Listen for PairCreated event.12 |
| Uniswap V2 | Pair | *(Dynamic)* | Holds liquidity for a token pair. | Use getPair(tokenA, tokenB) on factory.12 |
| Uniswap V3 | UniswapV3Factory | 0x1F98431c8aD98523631AE4a59f267346ea31F984 | Deploys new V3 pools. | N/A (Factory is static).1 |
| Uniswap V3 | UniversalRouter | 0x66a9893cc07d91d95644aedd05d03f95e1dba8af | Aggregates swaps and liquidity, handles ERC20 and NFTs. | N/A (Router is static).1 |
| Aave V3 | PoolAddressesProvider | *(Query)* | Immutable registry for all V3 contract addresses. | The entry point for fetching all other addresses.4 |
| Aave V3 | Pool | *(Dynamic)* | Main user-facing contract for all lending actions. | Fetch address from PoolAddressesProvider.5 |
| Aave V3 | PoolConfigurator | *(Dynamic)* | Administrative contract for pool configuration. | Fetch address from PoolAddressesProvider.5 |

### **3.3 Balancer: The Vault-Centric AMM**

Balancer's architecture is defined by its central Vault contract, which consolidates liquidity from all pools. This design has direct implications for how transactions are identified and classified.

#### **3.3.1 Balancer V2/V3 Core Contracts**

The Vault is the single most important contract for Balancer V2 and V3. Its address is 0xBA12222222228d8ba445958a75a0704d566BF2c8 on Polygon, but its canonical deployment addresses are maintained in the balancer-deployments GitHub repository, an official source for all protocol contracts.15 The

Vault is the sole recipient of user funds for swaps, adding liquidity, and removing liquidity.2 Pool contracts, in this system, are stateless and contain only the logic for their specific AMM model (e.g., Weighted, Stable). A transaction's

to address will always be the Vault.3 The true nature of the transaction is revealed by the

callData, which specifies the poolId and the action being performed. The Batch Relayer is a peripheral contract, with multiple versions listed in the documentation, that facilitates complex multi-step operations in a single transaction to save gas.15

To build a classification system for Balancer, a developer must implement a sophisticated callData decoder. A transaction targeting the Vault is not a simple action; it could be a swap, a liquidity provision, or a complex batch of operations. Parsing the input field of these transactions using the protocol's ABI is the only reliable way to understand the user's intent and provide an accurate classification.3

### **3.4 1inch: The Swap Aggregator**

1inch is a DEX aggregator that routes trades through various liquidity sources to find the best price. Its on-chain presence is primarily through a few key router contracts that execute off-chain generated instructions.

#### **3.4.1 Aggregation Protocol Contracts**

The Aggregation Router V6 is the primary entry point for all 1inch swaps. Its address on Ethereum mainnet is 0x111111125421cA6dc452d289314280a0f8842A65.13 The 1inch developer portal provides a list of helper contracts that this router uses to interact with specific protocols like Uniswap V3, Kyber, and others.13 A transaction targeting this router is an instruction to perform a complex, multi-hop swap. The

input data of these transactions is a highly encoded set of commands that were pre-calculated by the 1inch API to find the optimal path. The newer Fusion protocol, which enables MEV-protected swaps, also has its own set of contracts like the Fee Bank and Settlement Extension.13

For a backend service, classifying a transaction as a "1inch swap" is a good first step. A more advanced service would need to parse the callData to trace the individual swaps that the router executed on the underlying protocols. This provides a more granular view of the transaction and offers deeper insights into the liquidity sources used.

### **3.5 Paraswap: The API-Driven Aggregator**

Similar to 1inch, Paraswap is a DEX aggregator that relies on off-chain computation to optimize trade execution on-chain.

#### **3.5.1 Core Aggregation Contracts**

The main contract for executing swaps on Paraswap is the Augustus Swapper, with a V5 version identified in Etherscan data on networks like OP Mainnet.18 The Paraswap documentation explicitly states that transactions for its

swap function are executed with callData provided by the Paraswap API.8 This design highlights a fundamental dependency: the on-chain contract is a mere executor of off-chain logic.

A transaction targeting a Paraswap contract should be classified as an aggregated trade. Understanding the full details of the trade, such as the specific pools and routes used, would require decoding the complex callData provided by the API.8 This is an advanced feature that goes beyond simple transaction classification.

**Table 2: 1inch and Paraswap Key Contracts**

| Protocol | Contract Name | Address | Notes on Function/Role | Key Insights |
| :---- | :---- | :---- | :---- | :---- |
| 1inch | Aggregation Router V6 | 0x111111125421cA6dc452d289314280a0f8842A65 | The canonical router for all swaps and liquidity interactions. | CallData contains encoded instructions for a multi-DEX trade path. |
| Paraswap | Augustus Swapper V5 | 0xdef171fe48cf0115b1d80b88dc8eab59176fee57 (OP Mainnet) | Executes swaps based on callData from the Paraswap API. | The transaction's input data must be parsed to understand the underlying trade path. |

### **3.6 Euler: The Modular Lending Protocol**

Euler is a lending protocol that uses a modular design, with contract addresses publicly available in an official GitHub repository.

#### **3.6.1 Euler V2 Core Contracts**

The primary source for all Euler contract addresses is the euler-interfaces GitHub repository.6 The documentation explicitly warns developers to use only addresses from this repository or the official Euler docs to prevent phishing attempts.19 The protocol's core components include the

evaultFactory at 0x29a56a1b8214D9Cf7c5561811750D5cBDb45CC8e and the swapper at 0x2Bba09866b6F1025258542478C39720A09B728bF.6 The

EUL governance token is at 0xd9Fcd98c322942075A5C3860693e9f4f03AAE07b.6

For a backend service, this approach to address management dictates a specific workflow. The system should be designed to pull and parse the contract addresses directly from the official Euler GitHub repository, rather than relying on a hardcoded list. This ensures the data is always up-to-date with any new deployments or changes in the protocol's architecture.

### **3.7 Silo: Risk-Isolated Lending Markets**

Silo Finance is a lending protocol designed to contain risk by creating isolated lending markets for each asset pair. A key design element is the use of a "bridge asset," typically a stablecoin or ETH, to connect these markets.

#### **3.7.1 Silo V2 Core Contracts**

The SiloFactory is a crucial contract responsible for deploying new isolated lending markets, or "Silos." Etherscan data on a "Silo: Deployer" address confirms its role in creating various contracts, including SiloToken and SiloGovernanceTokenV2.20 An Etherscan entry for a "Silo: Factory" provides a mainnet address of

0xfccc27aabd0ab7a0b2ad2b7760037b1eab61616b.21 A

Router contract, deployed on a chain like OP Mainnet at 0xc66d2a90c37c873872281a05445ec0e9e82c76a9, facilitates complex interactions across different silos.22 The

xSILO governance and reward token is located at 0xdd4c6fd31ccf66e250790643947675153c221a91 on Ethereum mainnet.23

The unique architecture of Silo requires a classification strategy that accounts for both the individual Silo contracts and the unifying "bridge assets" they use. While transactions may target a specific Silo contract address, a significant portion of the protocol's activity will involve one of these core bridge assets, such as ETH or USDC.10 A robust classification system should therefore not only identify the specific

Silo address but also recognize the involvement of these bridge assets to provide a richer, more comprehensive view of user activity.

**Table 3: Balancer, Euler, and Silo Key Contracts**

| Protocol | Contract Name | Address | Notes on Function/Role | How to Find Dynamic Addresses |
| :---- | :---- | :---- | :---- | :---- |
| Balancer V2/V3 | Vault | *(Canonical, see text)* | Central hub for all token accounting; all swaps, joins, exits target this address. | N/A (Address is canonical).2 |
| Balancer V2/V3 | Pools | *(Dynamic)* | Contains only pool logic, not assets. Addresses are dynamic. | Query on-chain state or process events from factory contracts.15 |
| Balancer V2/V3 | Batch Relayer | *(Varies)* | Peripheral contract for complex, multi-step operations. | Addresses are listed in balancer-deployments GitHub repo.15 |
| Euler V2 | eVaultFactory | 0x29a56a1b8214D9Cf7c5561811750D5cBDb45CC8e | Deploys new vaults for lending markets. | Addresses are sourced from euler-interfaces GitHub repo.6 |
| Silo V2 | SiloFactory | 0xfccc27aabd0ab7a0b2ad2b7760037b1eab61616b | Deploys new isolated lending markets. | Monitor for deployment events from this factory.21 |
| Silo V2 | Silo | *(Dynamic)* | Individual lending market contract for a token pair. | Addresses are deployed by SiloFactory.10 |
| Silo V2 | Router | 0xc66d2a90c37c873872281a05445ec0e9e82c76a9 (OP Mainnet) | Facilitates interactions between different silos. | Address is semi-static per-chain, but dynamic discovery may be needed for future versions.22 |

## **4\. Transaction Classification Strategies**

Building a robust transaction classification service requires a multi-layered approach that moves beyond simple address matching. This section outlines a strategy for translating the protocol-specific architectural knowledge into actionable logic for a backend service.

### **4.1 The Importance of the Transaction to Address**

The to address is the first and most fundamental piece of data in any EVM transaction. For protocols that use a centralized entry point, such as Balancer's Vault or 1inch's Aggregation Router V6, the to address serves as the primary filter for identifying protocol-specific activity. For Uniswap V2 and V3, the to address will be a dynamic pool contract, requiring the backend service to maintain an up-to-date and comprehensive database of all known liquidity pools. In lending protocols like Aave, the to address will be the main Pool contract, which must be dynamically resolved from the PoolAddressesProvider to ensure the application is interacting with the current version of the protocol's contracts.4

### **4.2 Decoding the Transaction Input (callData)**

Once a transaction's to address has been matched to a protocol, the next layer of analysis involves decoding the input field. The input data contains the function selector and any encoded arguments. The function selector, which is the first four bytes of the input field, can be used to determine the specific action the user intended to perform (e.g., swap, deposit, addLiquidity).25

For protocols like Balancer and the aggregators (1inch, Paraswap), decoding the rest of the input field is critical. For Balancer, the callData will contain the poolId and a breakdown of the specific trade or liquidity action being performed within the Vault.3 For 1inch and Paraswap, the

callData encodes the entire trade path, which may involve multiple swaps across different underlying DEXs. A comprehensive classification service must be able to parse this complex data to provide a detailed breakdown of the transaction's components.8

### **4.3 The Role of Event Logs**

Event logs provide a reliable and immutable source of truth for on-chain activity. For protocols that use the factory pattern, like Uniswap, monitoring the PairCreated or PoolCreated events is the definitive method for discovering and tracking new liquidity pools.12 Events can also serve as a redundant verification layer for state-changing operations, as they provide a canonical record of swaps, deposits, and other user actions. By indexing these events, a backend service can ensure the integrity of its data and accurately track the evolution of protocol activity.

## **5\. Recommendations and Conclusion**

### **5.1 Actionable Recommendations for the User's Backend**

Based on this analysis, several key recommendations are provided for building a robust and high-fidelity transaction classification service.

* **Adopt Dynamic Address Resolution:** The practice of hardcoding addresses for protocols like Aave and Euler is a security and reliability risk. The backend service should be designed to query Aave's PoolAddressesProvider and parse Euler's euler-interfaces GitHub repository to fetch the latest contract addresses dynamically. This approach ensures that the application remains compatible with the protocol even after governance-driven upgrades or updates.  
* **Prioritize Call Data Decoding for Aggregators and Vaults:** For Balancer, 1inch, and Paraswap, simply matching the to address is insufficient. The core classification logic must be built to decode the transaction's input data to understand the specific action. This is the only way to distinguish between a swap and a liquidity action in Balancer's Vault, or to understand the complex trade path of an aggregated swap on 1inch or Paraswap.  
* **Implement an Event-Driven Indexing Service:** For a protocol like Uniswap, where new liquidity pools are created in a permissionless manner, a static list of addresses is insufficient. The backend service should include an event-driven indexer that monitors the factory contracts for PairCreated or PoolCreated events. This ensures the database of known contracts is always comprehensive and up-to-date.  
* **Build a Security-First Data Pipeline:** The diversity of DeFi architectures means a one-size-fits-all approach is not viable. The user's backend should treat each protocol uniquely. For instance, the system must account for the off-chain reliance of aggregators and the centralized nature of Balancer's vault. A multi-faceted pipeline that uses a combination of to address filtering, callData decoding, and event log monitoring is essential for high-match-rate and reliable classification.

### **5.2 Conclusion: The Road to a Robust DeFi Data Service**

This report has provided the foundational knowledge required to build a high-match-rate transaction classification service for blue-chip DeFi protocols. The analysis demonstrates that a successful implementation requires a deep understanding of each protocol's unique architectural model, a system for dynamic discovery of addresses, and sophisticated on-chain data parsing capabilities. By following these principles, the user can build a resilient, accurate, and scalable backend service for their DeFi portfolio application, ensuring that their service can adapt and grow with the evolving landscape of decentralized finance.

#### **Works cited**

1. Ethereum Deployments \- Uniswap Docs, accessed September 8, 2025, [https://docs.uniswap.org/contracts/v3/reference/deployments/ethereum-deployments](https://docs.uniswap.org/contracts/v3/reference/deployments/ethereum-deployments)  
2. The Vault \- Balancer Docs, accessed September 8, 2025, [https://docs.balancer.fi/concepts/vault/](https://docs.balancer.fi/concepts/vault/)  
3. Vault \- Balancer DOCS, accessed September 8, 2025, [https://docs-v2.balancer.fi/concepts/vault/](https://docs-v2.balancer.fi/concepts/vault/)  
4. Pool Addresses Provider | Aave Protocol Documentation, accessed September 8, 2025, [https://aave.com/docs/developers/smart-contracts/pool-addresses-provider](https://aave.com/docs/developers/smart-contracts/pool-addresses-provider)  
5. Smart Contracts | Aave Protocol Documentation, accessed September 8, 2025, [https://aave.com/docs/developers/smart-contracts](https://aave.com/docs/developers/smart-contracts)  
6. Contract Addresses | Euler Docs, accessed September 8, 2025, [https://docs.euler.finance/developers/contract-addresses/](https://docs.euler.finance/developers/contract-addresses/)  
7. Addresses and interface definitions for interacting with the Euler protocols \- GitHub, accessed September 8, 2025, [https://github.com/euler-xyz/euler-interfaces](https://github.com/euler-xyz/euler-interfaces)  
8. PARASWAP-V5 \- Instadapp Docs, accessed September 8, 2025, [https://docs.instadapp.io/connectors/mainnet/paraswap](https://docs.instadapp.io/connectors/mainnet/paraswap)  
9. paraswap/sdk \- UNPKG, accessed September 8, 2025, [https://app.unpkg.com/@paraswap/sdk@6.10.0/files/src/methods/swap/rates.ts](https://app.unpkg.com/@paraswap/sdk@6.10.0/files/src/methods/swap/rates.ts)  
10. Silo Finance \- ETHGlobal, accessed September 8, 2025, [https://ethglobal.com/showcase/silo-finance-11v1e](https://ethglobal.com/showcase/silo-finance-11v1e)  
11. 1inch API for wallets, dApps, and crypto swap platforms, accessed September 8, 2025, [https://1inch.io/page-api/](https://1inch.io/page-api/)  
12. Factory | Uniswap, accessed September 8, 2025, [https://docs.uniswap.org/contracts/v2/reference/smart-contracts/factory](https://docs.uniswap.org/contracts/v2/reference/smart-contracts/factory)  
13. documentation \- Dev Portal, accessed September 8, 2025, [https://portal.1inch.dev/documentation/contracts/aggregation-protocol/aggregation-introduction](https://portal.1inch.dev/documentation/contracts/aggregation-protocol/aggregation-introduction)  
14. Aave: Pool V3 | Address: 0x794a6135...b5b4814aD | PolygonScan, accessed September 8, 2025, [https://polygonscan.com/address/0x794a61358D6845594F94dc1DB02A252b5b4814aD](https://polygonscan.com/address/0x794a61358D6845594F94dc1DB02A252b5b4814aD)  
15. balancer/balancer-deployments \- GitHub, accessed September 8, 2025, [https://github.com/balancer/balancer-deployments](https://github.com/balancer/balancer-deployments)  
16. balancer-labs/v2-deployments \- NPM, accessed September 8, 2025, [https://www.npmjs.com/package/@balancer-labs/v2-deployments](https://www.npmjs.com/package/@balancer-labs/v2-deployments)  
17. Aggregation Router V6 | Address: 0x11111112...0f8842a65 | Etherscan, accessed September 8, 2025, [https://etherscan.io/address/0x111111125421ca6dc452d289314280a0f8842a65](https://etherscan.io/address/0x111111125421ca6dc452d289314280a0f8842a65)  
18. Paraswap v5: Augustus Swapper | Address: 0xdef171fe...9176fee57 | OP Mainnet Etherscan, accessed September 8, 2025, [https://optimistic.etherscan.io/address/0xdef171fe48cf0115b1d80b88dc8eab59176fee57](https://optimistic.etherscan.io/address/0xdef171fe48cf0115b1d80b88dc8eab59176fee57)  
19. Addresses | Euler Docs, accessed September 8, 2025, [https://docs.euler.finance/EUL/addresses/](https://docs.euler.finance/EUL/addresses/)  
20. Silo: Deployer | Address: 0x3e61fa24...c786206ec | Etherscan, accessed September 8, 2025, [https://etherscan.io/address/0x3e61fa24520c2754593b4544acb936bc786206ec](https://etherscan.io/address/0x3e61fa24520c2754593b4544acb936bc786206ec)  
21. Address: 0xfccc27aa...eab61616b | Etherscan, accessed September 8, 2025, [https://etherscan.io/address/0xfccc27aabd0ab7a0b2ad2b7760037b1eab61616b](https://etherscan.io/address/0xfccc27aabd0ab7a0b2ad2b7760037b1eab61616b)  
22. Silo: Router | Address: 0xc66d2a90...9e82c76a9 | OP Mainnet Etherscan, accessed September 8, 2025, [https://optimistic.etherscan.io/address/0xc66d2a90c37c873872281a05445ec0e9e82c76a9](https://optimistic.etherscan.io/address/0xc66d2a90c37c873872281a05445ec0e9e82c76a9)  
23. xSILO | Silo V2, accessed September 8, 2025, [https://docs.silo.finance/docs/users/tokenomics/xsilo/](https://docs.silo.finance/docs/users/tokenomics/xsilo/)  
24. What Is Silo Finance? DeFi's Risk-Isolated Lending Markets \- Nansen, accessed September 8, 2025, [https://www.nansen.ai/post/what-is-silo-finance-defis-risk-isolated-lending-markets](https://www.nansen.ai/post/what-is-silo-finance-defis-risk-isolated-lending-markets)  
25. paraswap/dex-lib \- NPM, accessed September 8, 2025, [https://www.npmjs.com/package/@paraswap/dex-lib](https://www.npmjs.com/package/@paraswap/dex-lib)