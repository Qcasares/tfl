# /// script
# dependencies = [
#   "mcp",
#   "httpx",
#   "python-dotenv"
# ]
# ///

import os
import asyncio
from typing import Any, Optional
from datetime import datetime
import httpx
from dotenv import load_dotenv
import mcp.types as types
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
import mcp.server.stdio

# Load environment variables from .env file
load_dotenv()

# TfL API configuration
TFL_API_BASE = "https://api.tfl.gov.uk"
APP_KEY = os.getenv("TFL_APP_KEY")
APP_ID = os.getenv("TFL_APP_ID")

# Initialize server
server = Server("tfl-server")

async def make_tfl_request(client: httpx.AsyncClient, endpoint: str, params: dict = None) -> dict[str, Any] | None:
    """Make a request to the TfL API with proper error handling."""
    default_params = {
        "app_key": APP_KEY,
        "app_id": APP_ID
    }
    
    if params:
        default_params.update(params)
        
    try:
        response = await client.get(
            f"{TFL_API_BASE}/{endpoint}",
            params=default_params,
            timeout=30.0
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error making TfL request: {str(e)}")
        return None

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """List available tools for querying TfL data."""
    return [
        types.Tool(
            name="get-line-status",
            description="Get the current status of specified London transport lines",
            inputSchema={
                "type": "object",
                "properties": {
                    "lines": {
                        "type": "string",
                        "description": "Comma-separated list of line names (e.g., victoria,northern,central)",
                    }
                },
                "required": ["lines"]
            }
        ),
        types.Tool(
            name="get-arrivals",
            description="Get arrival predictions for a specific station",
            inputSchema={
                "type": "object",
                "properties": {
                    "station": {
                        "type": "string",
                        "description": "Station name or ID",
                    }
                },
                "required": ["station"]
            }
        ),
        types.Tool(
            name="search-bike-points",
            description="Search for bike points near a location",
            inputSchema={
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "Location name in London",
                    }
                },
                "required": ["location"]
            }
        ),
        types.Tool(
            name="get-station-info",
            description="Get detailed information about a specific station including facilities, lines, and accessibility",
            inputSchema={
                "type": "object",
                "properties": {
                    "station": {
                        "type": "string",
                        "description": "Station name or ID",
                    }
                },
                "required": ["station"]
            }
        ),
        types.Tool(
            name="find-stops-by-radius",
            description="Find stops within a specified radius of a location",
            inputSchema={
                "type": "object",
                "properties": {
                    "lat": {
                        "type": "number",
                        "description": "Latitude of the center point",
                    },
                    "lon": {
                        "type": "number",
                        "description": "Longitude of the center point",
                    },
                    "radius": {
                        "type": "number",
                        "description": "Radius in meters (max 1000)",
                    }
                },
                "required": ["lat", "lon", "radius"]
            }
        )
    ]

def format_line_status(line_data: dict) -> str:
    """Format line status data into a readable string."""
    name = line_data.get("name", "Unknown Line")
    status = "Unknown"
    reason = ""
    
    if statuses := line_data.get("lineStatuses", []):
        status = statuses[0].get("statusSeverityDescription", "Unknown")
        reason = statuses[0].get("reason", "")
    
    formatted = f"Line: {name}\nStatus: {status}"
    if reason:
        formatted += f"\nReason: {reason}"
    return formatted + "\n---"

def format_arrival(arrival: dict) -> str:
    """Format arrival prediction data into a readable string."""
    line = arrival.get("lineName", "Unknown Line")
    destination = arrival.get("destinationName", "Unknown Destination")
    platform = arrival.get("platformName", "Unknown Platform")
    
    # Convert timestamp to minutes
    try:
        expected_arrival = datetime.fromisoformat(arrival.get("expectedArrival", "").replace("Z", "+00:00"))
        now = datetime.now().astimezone()
        minutes = int((expected_arrival - now).total_seconds() / 60)
        time_desc = f"{minutes} minutes" if minutes > 0 else "Due"
    except:
        time_desc = "Time unknown"
    
    return f"Line: {line}\nPlatform: {platform}\nDestination: {destination}\nArrival: {time_desc}\n---"

def format_bike_point(point: dict) -> str:
    """Format bike point data into a readable string."""
    name = point.get("commonName", "Unknown Location")
    bikes = point.get("additionalProperties", [])
    
    bikes_available = "Unknown"
    docks_available = "Unknown"
    
    for prop in bikes:
        if prop.get("key") == "NbBikes":
            bikes_available = prop.get("value", "Unknown")
        elif prop.get("key") == "NbEmptyDocks":
            docks_available = prop.get("value", "Unknown")
    
    return (
        f"Location: {name}\n"
        f"Bikes Available: {bikes_available}\n"
        f"Empty Docks: {docks_available}\n"
        "---"
    )

def format_station_info(station_data: dict) -> str:
    """Format detailed station information into a readable string."""
    name = station_data.get("commonName", "Unknown Station")
    modes = ", ".join(station_data.get("modes", []))
    zones = ", ".join(str(zone) for zone in station_data.get("zones", []))
    
    # Get facilities
    facilities = []
    for additional in station_data.get("additionalProperties", []):
        if additional.get("category") == "Facility":
            facilities.append(additional.get("key", ""))

    # Get lines serving this station
    lines = [line.get("name", "") for line in station_data.get("lines", [])]
    
    # Get accessibility information
    accessibility = []
    for additional in station_data.get("additionalProperties", []):
        if additional.get("category") == "Accessibility":
            accessibility.append(additional.get("key", ""))

    formatted = (
        f"Station: {name}\n"
        f"Transport Modes: {modes}\n"
        f"Zones: {zones}\n"
        f"Lines: {', '.join(lines)}\n"
    )

    if facilities:
        formatted += f"Facilities: {', '.join(facilities)}\n"
    
    if accessibility:
        formatted += f"Accessibility: {', '.join(accessibility)}\n"
        
    return formatted + "---"

def format_nearby_stop(stop: dict) -> str:
    """Format nearby stop information into a readable string."""
    name = stop.get("commonName", "Unknown Location")
    distance = stop.get("distance", 0)
    modes = ", ".join(stop.get("modes", []))
    lines = [line.get("name", "") for line in stop.get("lines", [])]
    
    return (
        f"Stop: {name}\n"
        f"Distance: {distance:.0f}m\n"
        f"Modes: {modes}\n"
        f"Lines: {', '.join(lines)}\n"
        "---"
    )

@server.call_tool()
async def handle_call_tool(
    name: str, 
    arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """Handle tool execution requests."""
    if not arguments:
        raise ValueError("Missing arguments")
        
    async with httpx.AsyncClient() as client:
        if name == "get-line-status":
            lines = arguments.get("lines", "").strip()
            if not lines:
                raise ValueError("Lines parameter must not be empty")
                
            lines_list = [line.strip() for line in lines.split(",")]
            statuses_data = await make_tfl_request(client, f"Line/{','.join(lines_list)}/Status")
            
            if not statuses_data:
                return [types.TextContent(
                    type="text",
                    text="Failed to retrieve line statuses"
                )]
                
            formatted_statuses = [format_line_status(line) for line in statuses_data]
            
            return [types.TextContent(
                type="text",
                text="Current Line Statuses:\n\n" + "\n".join(formatted_statuses)
            )]
            
        elif name == "get-arrivals":
            station = arguments.get("station", "").strip()
            if not station:
                raise ValueError("Station parameter must not be empty")
                
            # First try to get the station ID
            search_result = await make_tfl_request(
                client, 
                f"StopPoint/Search/{station}",
                {"modes": "tube,overground,dlr"}
            )
            
            if not search_result or not search_result.get("matches"):
                return [types.TextContent(
                    type="text",
                    text=f"Could not find station: {station}"
                )]
                
            station_id = search_result["matches"][0]["id"]
            arrivals_data = await make_tfl_request(client, f"StopPoint/{station_id}/Arrivals")
            
            if not arrivals_data:
                return [types.TextContent(
                    type="text",
                    text=f"Failed to retrieve arrivals for {station}"
                )]
                
            # Sort by expected arrival time
            arrivals_data.sort(key=lambda x: x.get("expectedArrival", ""))
            formatted_arrivals = [format_arrival(arrival) for arrival in arrivals_data[:10]]  # Show next 10 arrivals
            
            return [types.TextContent(
                type="text",
                text=f"Next arrivals at {station}:\n\n" + "\n".join(formatted_arrivals)
            )]
            
        elif name == "search-bike-points":
            location = arguments.get("location", "").strip()
            if not location:
                raise ValueError("Location parameter must not be empty")
                
            search_result = await make_tfl_request(
                client,
                f"BikePoint/Search",
                {"query": location}
            )
            
            if not search_result:
                return [types.TextContent(
                    type="text",
                    text=f"Failed to search for bike points near {location}"
                )]
                
            if not search_result:
                return [types.TextContent(
                    type="text",
                    text=f"No bike points found near {location}"
                )]
                
            formatted_points = [format_bike_point(point) for point in search_result[:5]]  # Show 5 nearest points
            
            return [types.TextContent(
                type="text",
                text=f"Bike points near {location}:\n\n" + "\n".join(formatted_points)
            )]

        elif name == "get-station-info":
            station = arguments.get("station", "").strip()
            if not station:
                raise ValueError("Station parameter must not be empty")
            
            # First search for the station to get its ID
            search_result = await make_tfl_request(
                client,
                f"StopPoint/Search/{station}",
                {"modes": "tube,overground,dlr"}
            )
            
            if not search_result or not search_result.get("matches"):
                return [types.TextContent(
                    type="text",
                    text=f"Could not find station: {station}"
                )]
            
            station_id = search_result["matches"][0]["id"]
            
            # Get detailed station information
            station_data = await make_tfl_request(client, f"StopPoint/{station_id}")
            
            if not station_data:
                return [types.TextContent(
                    type="text",
                    text=f"Failed to retrieve information for {station}"
                )]
            
            return [types.TextContent(
                type="text",
                text=format_station_info(station_data)
            )]

        elif name == "find-stops-by-radius":
            lat = arguments.get("lat")
            lon = arguments.get("lon")
            radius = min(arguments.get("radius", 1000), 1000)  # Cap radius at 1000m
            
            if not all(x is not None for x in [lat, lon, radius]):
                raise ValueError("Missing required parameters")
            
            # Get stops within radius
            stops_data = await make_tfl_request(
                client,
                f"StopPoint",
                {
                    "lat": lat,
                    "lon": lon,
                    "radius": radius,
                    "modes": "tube,overground,dlr"
                }
            )
            
            if not stops_data or "stopPoints" not in stops_data:
                return [types.TextContent(
                    type="text",
                    text=f"Failed to find stops within {radius}m of {lat}, {lon}"
                )]
            
            stops = stops_data["stopPoints"]
            if not stops:
                return [types.TextContent(
                    type="text",
                    text=f"No stops found within {radius}m of {lat}, {lon}"
                )]
            
            formatted_stops = [format_nearby_stop(stop) for stop in stops[:10]]  # Show closest 10 stops
            
            return [types.TextContent(
                type="text",
                text=f"Stops within {radius}m of {lat}, {lon}:\n\n" + "\n".join(formatted_stops)
            )]
            
        else:
            raise ValueError(f"Unknown tool: {name}")

@server.list_resources()
async def handle_list_resources() -> list[types.Resource]:
    """List available TfL data resources."""
    return [
        types.Resource(
            uri="tfl://lines",
            name="TfL Lines",
            description="List of all TfL lines and their basic information"
        ),
        types.Resource(
            uri="tfl://stations",
            name="TfL Stations",
            description="List of all TfL stations and their basic information"
        ),
        types.Resource(
            uri="tfl://modes",
            name="TfL Transport Modes",
            description="List of all available transport modes"
        )
    ]

@server.read_resource()
async def handle_read_resource(uri: str) -> str:
    """Handle resource read requests."""
    async with httpx.AsyncClient() as client:
        if uri == "tfl://lines":
            lines_data = await make_tfl_request(client, "Line/Mode/tube,overground,dlr")
            if not lines_data:
                return "Failed to retrieve lines data"
            
            formatted_lines = []
            for line in lines_data:
                formatted_lines.append(
                    f"Name: {line.get('name')}\n"
                    f"ID: {line.get('id')}\n"
                    f"Mode: {line.get('modeName')}\n"
                    f"Routes: {len(line.get('routeSections', []))}\n"
                    "---"
                )
            
            return "TfL Lines:\n\n" + "\n".join(formatted_lines)
            
        elif uri == "tfl://stations":
            # Get all tube, overground, and DLR stations
            stations_data = await make_tfl_request(
                client,
                "StopPoint/Mode/tube,overground,dlr"
            )
            
            if not stations_data or not stations_data.get("stopPoints"):
                return "Failed to retrieve stations data"
                
            formatted_stations = []
            for station in stations_data["stopPoints"][:50]:  # Limit to 50 stations for readability
                # Extract zone information
                zones = ", ".join(str(zone) for zone in station.get("zones", []))
                
                # Get lines serving this station
                lines = [line.get("name", "") for line in station.get("lines", [])]
                
                formatted_stations.append(
                    f"Name: {station.get('commonName')}\n"
                    f"ID: {station.get('id')}\n"
                    f"Modes: {', '.join(station.get('modes', []))}\n"
                    f"Zones: {zones}\n"
                    f"Lines: {', '.join(lines)}\n"
                    "---"
                )
            
            return "TfL Stations (first 50):\n\n" + "\n".join(formatted_stations)
            
        elif uri == "tfl://modes":
            modes_data = await make_tfl_request(client, "Mode")
            if not modes_data:
                return "Failed to retrieve transport modes data"
            
            formatted_modes = []
            for mode in modes_data:
                formatted_modes.append(
                    f"Name: {mode.get('modeName')}\n"
                    f"Description: {mode.get('description', 'No description available')}\n"
                    f"Is TfL Service: {'Yes' if mode.get('isTflService') else 'No'}\n"
                    f"Is Scheduled Service: {'Yes' if mode.get('isScheduledService') else 'No'}\n"
                    "---"
                )
            
            return "TfL Transport Modes:\n\n" + "\n".join(formatted_modes)
            
        else:
            raise ValueError(f"Unknown resource URI: {uri}")

async def main():
    """Run the server using stdin/stdout streams."""
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="tfl-server",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                )
            )
        )

if __name__ == "__main__":
    asyncio.run(main())