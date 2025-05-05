import React, { useState } from 'react';

const ArchitectureExplorer = () => {
  const [selectedComponent, setSelectedComponent] = useState(null);
  const [selectedView, setSelectedView] = useState('overview');

  // Architecture components data
  const components = {
    mcp: {
      name: 'Master Control Program (MCP)',
      description: 'Central orchestration component that manages agent registration and routes messages based on capabilities.',
      responsibilities: [
        'Agent registration and discovery',
        'Message routing to appropriate agents',
        'Maintaining agent status information',
        'Coordinating multi-agent workflows'
      ],
      technologies: ['FastAPI', 'Python', 'Async HTTP'],
      codeStructure: [
        '/mcp/api/main.py - FastAPI application setup',
        '/mcp/api/endpoints.py - API endpoint definitions',
        '/mcp/orchestration/registry.py - Agent registry implementation',
        '/mcp/orchestration/router.py - Message routing logic'
      ]
    },
    llm: {
      name: 'LLM Service',
      description: 'Service that provides access to Large Language Models with caching capabilities.',
      responsibilities: [
        'Loading and managing the language model',
        'Text generation based on prompts',
        'Caching responses for efficiency',
        'Managing model resources'
      ],
      technologies: ['FastAPI', 'Python', 'PyTorch', 'Transformers', 'Redis'],
      codeStructure: [
        '/llm-service/api/main.py - FastAPI application setup',
        '/llm-service/api/endpoints.py - Generation API endpoints',
        '/llm-service/Dockerfile - Multi-stage build for model loading'
      ]
    },
    incident: {
      name: 'Incident Analysis Agent',
      description: 'Agent that analyzes incident reports to provide structured insights, potential causes, and recommended actions.',
      responsibilities: [
        'Processing incident reports',
        'Generating prompts for the LLM service',
        'Parsing and structuring LLM responses',
        'Extracting actionable insights',
        'Caching analysis results'
      ],
      technologies: ['FastAPI', 'Python', 'SQLite', 'Pydantic'],
      codeStructure: [
        '/agents/incident/api/main.py - FastAPI application setup',
        '/agents/incident/models.py - Data models',
        '/agents/incident/analyzer.py - Core analysis logic',
        '/agents/incident/api/endpoints.py - API endpoint definitions'
      ]
    }
  };

  // View types
  const views = {
    overview: {
      name: 'System Overview',
      description: 'High-level overview of all system components and their interactions.'
    },
    sequence: {
      name: 'Sequence Diagram',
      description: 'Flow of messages and operations for processing an incident report.'
    },
    components: {
      name: 'Component Structure',
      description: 'Detailed internal structure of individual components.'
    },
    deployment: {
      name: 'Deployment Architecture',
      description: 'Docker-based deployment structure for the system components.'
    }
  };

  // Handler for view click
  const handleViewClick = (viewKey) => {
    setSelectedView(viewKey);
    setSelectedComponent(null); // Reset component selection when changing view
  };

  // Handler for component click
  const handleComponentClick = (componentKey) => {
    setSelectedComponent(componentKey);
  };

  // Render component details
  const renderComponentDetails = () => {
    if (!selectedComponent) {
      return (
        <div className="p-4 bg-gray-100 rounded-lg">
          <p className="text-gray-600">Select a component to see details</p>
        </div>
      );
    }

    const component = components[selectedComponent];

    return (
      <div className="p-4 bg-white rounded-lg shadow">
        <h2 className="text-xl font-bold text-blue-700 mb-2">{component.name}</h2>
        <p className="mb-4 text-gray-700">{component.description}</p>
        
        <h3 className="text-lg font-semibold text-blue-600 mb-2">Responsibilities</h3>
        <ul className="list-disc pl-5 mb-4">
          {component.responsibilities.map((resp, index) => (
            <li key={index} className="text-gray-700 mb-1">{resp}</li>
          ))}
        </ul>
        
        <h3 className="text-lg font-semibold text-blue-600 mb-2">Technologies</h3>
        <div className="flex flex-wrap gap-2 mb-4">
          {component.technologies.map((tech, index) => (
            <span key={index} className="px-2 py-1 bg-blue-100 text-blue-700 rounded-md text-sm">
              {tech}
            </span>
          ))}
        </div>
        
        <h3 className="text-lg font-semibold text-blue-600 mb-2">Code Structure</h3>
        <ul className="list-disc pl-5 mb-2">
          {component.codeStructure.map((file, index) => (
            <li key={index} className="text-gray-700 mb-1 font-mono text-sm">{file}</li>
          ))}
        </ul>
      </div>
    );
  };

  // Render view content
  const renderViewContent = () => {
    switch(selectedView) {
      case 'overview':
        return (
          <div className="p-4 bg-white rounded-lg shadow">
            <h2 className="text-xl font-bold text-blue-700 mb-2">System Overview</h2>
            <div className="bg-blue-50 p-4 rounded-lg mb-4 text-blue-800 text-sm">
              The ACS-AI-AGENTS project implements a multi-agent architecture with a central coordinator (MCP)
              that manages specialized AI agents focusing on specific GMAO tasks.
            </div>
            
            <p className="mb-4">
              External systems communicate with the Master Control Program (MCP), which routes
              requests to the appropriate specialized agents based on required capabilities.
              Agents can use shared services like the LLM Service for natural language processing.
            </p>
            
            <h3 className="text-lg font-semibold text-blue-600 mb-2">Key Components</h3>
            <ul className="list-disc pl-5 mb-4">
              <li className="mb-1">Master Control Program (MCP) - Central orchestration</li>
              <li className="mb-1">Incident Analysis Agent - Analysis of incident reports</li>
              <li className="mb-1">LLM Service - Natural language understanding and generation</li>
              <li className="mb-1">Redis Cache - Fast storage for LLM responses</li>
              <li className="mb-1">SQLite Cache - Incident analysis caching</li>
            </ul>
            
            <h3 className="text-lg font-semibold text-blue-600 mb-2">Planned Agents</h3>
            <ul className="list-disc pl-5">
              <li className="mb-1">Predictive Maintenance Agent</li>
              <li className="mb-1">Technician Assignment Agent</li>
              <li className="mb-1">Inventory Management Agent</li>
            </ul>
          </div>
        );
      
      case 'sequence':
        return (
          <div className="p-4 bg-white rounded-lg shadow">
            <h2 className="text-xl font-bold text-blue-700 mb-2">Incident Analysis Sequence</h2>
            <p className="mb-4">
              The sequence of operations for processing an incident report through the system:
            </p>
            
            <ol className="list-decimal pl-5 mb-4">
              <li className="mb-2">External system submits incident report to MCP</li>
              <li className="mb-2">MCP identifies Incident Analysis Agent as capable</li>
              <li className="mb-2">MCP routes the incident data to the agent</li>
              <li className="mb-2">Agent checks local cache for similar incidents</li>
              <li className="mb-2">If cache miss, agent formulates a prompt for the LLM</li>
              <li className="mb-2">Agent sends prompt to LLM Service</li>
              <li className="mb-2">LLM Service checks Redis cache and generates text if needed</li>
              <li className="mb-2">Agent receives and parses LLM response</li>
              <li className="mb-2">Agent extracts structured insights and calculates confidence</li>
              <li className="mb-2">Agent stores analysis in cache and returns results to MCP</li>
              <li className="mb-2">MCP returns structured analysis to the external system</li>
            </ol>
            
            <div className="bg-yellow-50 p-4 rounded-lg text-yellow-800 text-sm">
              This sequence implements multiple caching layers for efficiency, with a fallback
              to full LLM analysis when needed.
            </div>
          </div>
        );
      
      case 'components':
        return (
          <div className="p-4 bg-white rounded-lg shadow">
            <h2 className="text-xl font-bold text-blue-700 mb-2">Component Architecture</h2>
            <p className="mb-4">
              Each component in the system is structured as a microservice with its own API, 
              data models, and business logic. All components use FastAPI for consistent API design.
            </p>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
              <div className="border border-blue-200 rounded-lg p-3">
                <h3 className="font-semibold text-blue-600 mb-1">API Layer</h3>
                <p className="text-sm text-gray-700">Handles HTTP requests/responses and routing to business logic</p>
              </div>
              
              <div className="border border-green-200 rounded-lg p-3">
                <h3 className="font-semibold text-green-600 mb-1">Business Logic</h3>
                <p className="text-sm text-gray-700">Implements core functionality like analysis, routing, or generation</p>
              </div>
              
              <div className="border border-purple-200 rounded-lg p-3">
                <h3 className="font-semibold text-purple-600 mb-1">Data Models</h3>
                <p className="text-sm text-gray-700">Defines structured data objects with validation using Pydantic</p>
              </div>
              
              <div className="border border-orange-200 rounded-lg p-3">
                <h3 className="font-semibold text-orange-600 mb-1">Storage Layer</h3>
                <p className="text-sm text-gray-700">Manages persistence through SQLite, Redis, or other mechanisms</p>
              </div>
            </div>
            
            <p className="text-sm text-gray-600">
              Each component follows a similar structure while implementing its specific responsibilities.
            </p>
          </div>
        );
      
      case 'deployment':
        return (
          <div className="p-4 bg-white rounded-lg shadow">
            <h2 className="text-xl font-bold text-blue-700 mb-2">Deployment Architecture</h2>
            <p className="mb-4">
              The system is deployed using Docker containers orchestrated with Docker Compose.
            </p>
            
            <h3 className="text-lg font-semibold text-blue-600 mb-2">Containers</h3>
            <ul className="list-disc pl-5 mb-4">
              <li className="mb-1"><span className="font-semibold">redis:</span> Alpine-based Redis for caching</li>
              <li className="mb-1"><span className="font-semibold">llm-service:</span> LLM service with model loading</li>
              <li className="mb-1"><span className="font-semibold">mcp:</span> Master Control Program container</li>
              <li className="mb-1"><span className="font-semibold">incident-agent:</span> Incident Analysis Agent container</li>
            </ul>
            
            <h3 className="text-lg font-semibold text-blue-600 mb-2">Volumes</h3>
            <ul className="list-disc pl-5 mb-4">
              <li className="mb-1"><span className="font-semibold">redis_data:</span> Persists Redis cache</li>
              <li className="mb-1"><span className="font-semibold">incident_cache_db:</span> Persists SQLite incident cache</li>
            </ul>
            
            <h3 className="text-lg font-semibold text-blue-600 mb-2">Networking</h3>
            <p className="mb-2">
              All containers are connected to a Docker network and communicate using service names as hostnames.
              External access is provided via port mapping:
            </p>
            <ul className="list-disc pl-5">
              <li className="mb-1">LLM Service: Port 8001</li>
              <li className="mb-1">MCP: Port 8002</li>
              <li className="mb-1">Incident Agent: Port 8003</li>
              <li className="mb-1">Redis: Port 6379</li>
            </ul>
          </div>
        );
        
      default:
        return (
          <div className="p-4 bg-gray-100 rounded-lg">
            <p className="text-gray-600">Select a view to see content</p>
          </div>
        );
    }
  };

  return (
    <div className="max-w-6xl mx-auto p-4">
      <h1 className="text-2xl font-bold text-blue-800 mb-6">ACS-AI-AGENTS Architecture Explorer</h1>
      
      {/* View selector */}
      <div className="mb-6">
        <h2 className="text-lg font-semibold text-gray-700 mb-2">Select View</h2>
        <div className="flex flex-wrap gap-2">
          {Object.entries(views).map(([key, view]) => (
            <button
              key={key}
              onClick={() => handleViewClick(key)}
              className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                selectedView === key 
                  ? 'bg-blue-600 text-white' 
                  : 'bg-gray-200 hover:bg-gray-300 text-gray-800'
              }`}
            >
              {view.name}
            </button>
          ))}
        </div>
      </div>
      
      <div className="flex flex-col lg:flex-row gap-6">
        {/* Main content */}
        <div className="lg:w-2/3">
          {renderViewContent()}
        </div>
        
        {/* Components sidebar */}
        <div className="lg:w-1/3">
          <h2 className="text-lg font-semibold text-gray-700 mb-2">Components</h2>
          <div className="grid grid-cols-1 gap-2 mb-4">
            {Object.entries(components).map(([key, component]) => (
              <button
                key={key}
                onClick={() => handleComponentClick(key)}
                className={`p-3 text-left rounded-md transition-colors ${
                  selectedComponent === key 
                    ? 'bg-blue-100 border-l-4 border-blue-600' 
                    : 'bg-white hover:bg-gray-100 border-l-4 border-transparent'
                }`}
              >
                <h3 className="font-medium">{component.name}</h3>
                <p className="text-sm text-gray-600 truncate">{component.description}</p>
              </button>
            ))}
          </div>
          
          {/* Component details */}
          {renderComponentDetails()}
        </div>
      </div>
    </div>
  );
};

export default ArchitectureExplorer; 