# Model Context Protocol (MCP) Architecture

## Overview
The Model Context Protocol (MCP) is a protocol that enables AI applications to connect to context servers. It defines how clients and servers communicate to share contextual information with AI applications.

## Scope

The MCP includes:
- **MCP Specification**: Implementation requirements for clients and servers
- **MCP SDKs**: SDKs for different programming languages
- **MCP Development Tools**: Tools like the MCP Inspector
- **MCP Reference Server Implementations**: Reference implementations of MCP servers

## Key Participants

### MCP Host
The AI application that coordinates and manages one or multiple MCP clients (e.g., Claude Code, Claude Desktop, Visual Studio Code)

### MCP Client
A component that maintains a connection to an MCP server and obtains context from an MCP server for the MCP host to use

### MCP Server
A program that provides context to MCP clients. Can run locally or remotely:
- **Local servers**: Use STDIO transport, serve single client (e.g., filesystem server)
- **Remote servers**: Use Streamable HTTP transport, serve many clients (e.g., Sentry MCP server)

## Architecture Layers

MCP consists of two layers:

### 1. Data Layer (Inner Layer)
Defines the JSON-RPC 2.0 based protocol for client-server communication:

- **Lifecycle management**: Connection initialization, capability negotiation, and termination
- **Server features**: Tools, resources, and prompts
- **Client features**: Sampling, elicitation, and logging
- **Utility features**: Notifications and progress tracking

### 2. Transport Layer (Outer Layer)
Manages communication channels and authentication:

- **Stdio transport**: Uses standard input/output for local process communication (no network overhead)
- **Streamable HTTP transport**: Uses HTTP POST for client-to-server messages with optional Server-Sent Events for streaming (supports remote communication and standard HTTP authentication)

## Data Layer Protocol

### Primitives

#### Server Primitives (What servers expose):

1. **Tools**: Executable functions that AI applications can invoke
   - Examples: file operations, API calls, database queries
   - Methods: `tools/list`, `tools/call`

2. **Resources**: Data sources that provide contextual information
   - Examples: file contents, database records, API responses
   - Methods: `*/list`, `*/get`

3. **Prompts**: Reusable templates for structuring interactions
   - Examples: system prompts, few-shot examples
   - Methods: `*/list`, `*/get`

#### Client Primitives (What clients expose):

1. **Sampling**: Allows servers to request language model completions from the client's AI application
   - Method: `sampling/complete`

2. **Elicitation**: Allows servers to request additional information from users
   - Method: `elicitation/request`

3. **Logging**: Enables servers to send log messages to clients for debugging

#### Utility Primitives:

- **Tasks (Experimental)**: Durable execution wrappers for deferred result retrieval and status tracking

### Notifications

Real-time notifications enable dynamic updates between servers and clients. Sent as JSON-RPC 2.0 notification messages without expecting a response.

## Example Use Case

An MCP server providing database context can:
- Expose **tools** for querying the database
- Provide a **resource** containing the database schema
- Include a **prompt** with few-shot examples for interacting with the tools

## Communication Protocol

- Uses JSON-RPC 2.0 as the underlying RPC protocol
- Clients and servers send requests and respond accordingly
- Notifications used when no response is required
- Discovery pattern: Clients use `*/list` methods to discover available primitives dynamically
