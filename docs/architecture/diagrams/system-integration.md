# System Integration Diagram

```mermaid
flowchart LR
    subgraph GMAO[GMAO System]
        IM[Incident Management]
        WO[Work Orders]
        Inv[Inventory]
    end

    subgraph ACS[ACS-AI-AGENTS]
        subgraph MCP[Master Control Program]
            Registry[(Agent Registry)]
            Router[Message Router]
        end

        subgraph Agents[Agent Modules]
            IAA["Incident Analysis<br>Agent"]
            PMA["Predictive Maintenance<br>Agent (Planned)"]
            TAA["Technician Assignment<br>Agent (Planned)"]
            IMA["Inventory Management<br>Agent (Planned)"]
        end

        subgraph LLMSvc[LLM Service]
            LLMAPI[Generation API]
            Model[Language Model]
            Cache[(Redis Cache)]
        end
    end

    IM -- Incidents --> MCP
    WO -- Schedules --> MCP
    Inv -- Stock Levels --> MCP

    MCP -- Register --> IAA
    MCP -- Incidents --> IAA
    IAA -- Analyze --> LLMSvc
    LLMSvc -- Results --> IAA
    IAA -- Insights --> MCP
    MCP -- Actions --> GMAO

    MCP -.- PMA
    MCP -.- TAA
    MCP -.- IMA

    classDef existing fill:#9f9,stroke:#484
    classDef planned fill:#ff9,stroke:#994
    classDef external fill:#99f,stroke:#449

    class GMAO,IM,WO,Inv external
    class MCP,Registry,Router,IAA,LLMSvc,LLMAPI,Model,Cache existing
    class PMA,TAA,IMA planned
``` 