# System Architecture

```mermaid
flowchart TD
    subgraph External["External Systems"]
        GMAO[GMAO System]
        Monitor[Monitoring Tools]
    end

    subgraph ACS["ACS-AI-AGENTS"]
        MCP[Master Control Program]

        subgraph Agents["Agent Modules"]
            IAA[Incident Analysis Agent]
            PMA[Predictive Maintenance Agent
(Planned)]
            TAA[Technician Assignment Agent
(Planned)]
            IMA[Inventory Management Agent
(Planned)]
        end

        subgraph Services["Shared Services"]
            LLM[LLM Service]
            Redis[(Redis Cache)]
        end
    end

    External --> MCP
    MCP --> Agents
    MCP -- Register --> IAA
    IAA -- Call --> LLM
    LLM -- Cache --> Redis

    classDef implemented fill:#9f9,stroke:#484
    classDef planned fill:#ff9,stroke:#994
    classDef service fill:#99f,stroke:#449
    classDef storage fill:#fc9,stroke:#ca4

    class MCP,IAA,LLM implemented
    class PMA,TAA,IMA planned
    class LLM service
    class Redis storage
``` 