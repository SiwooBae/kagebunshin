# KageBunshin Filesystem Operations Guide

## Overview

KageBunshin agents have secure filesystem capabilities that allow them to read, write, organize, and manage files within a sandboxed environment. This guide explains how to effectively use these capabilities for various tasks.

## 🛡️ Security Model

### Sandbox Isolation
- **Containment**: All file operations are restricted to your designated sandbox directory
- **Path Validation**: Path traversal attempts (`../`) are automatically blocked
- **Extension Filtering**: Only whitelisted file types can be created or accessed
- **Size Limits**: File size restrictions prevent resource exhaustion
- **Isolation**: Each agent gets its own sandbox to prevent interference

### Sandbox Structure
```
~/.kagebunshin/workspace/           # Main sandbox root
├── agent_primary_agent/            # Primary agent's sandbox
│   ├── data/                       # User data files
│   ├── reports/                    # Generated reports
│   └── clones/                     # Cloned agent sandboxes
│       ├── agent_clone_1/          # Clone 1's isolated space
│       └── agent_clone_2/          # Clone 2's isolated space
└── agent_another_agent/            # Different agent family
    └── ...
```

## 🔧 Available Tools

### 1. `read_file(path)`
Read the contents of a text file.

**Parameters:**
- `path` (str): Relative path to file within sandbox

**Returns:**
JSON with status, content, file metadata

**Example Usage:**
```python
# Read a configuration file
config_result = read_file("config/settings.json")
if config_result["status"] == "success":
    config_data = config_result["content"]
    # Process the configuration...
```

**Common Use Cases:**
- Loading previously saved data or configurations
- Reading input files for processing
- Accessing templates or reference data
- Importing data from external sources

---

### 2. `write_file(path, content)`
Write content to a file (creates or overwrites).

**Parameters:**
- `path` (str): Relative path for the file
- `content` (str): Text content to write

**Returns:**
JSON with status, bytes written, operation type

**Example Usage:**
```python
# Save analysis results
results_json = json.dumps({"findings": ["item1", "item2"]})
write_result = write_file("analysis/results.json", results_json)
if write_result["status"] == "success":
    print(f"Saved {write_result['bytes_written']} bytes")
```

**Common Use Cases:**
- Saving processed data and analysis results
- Creating reports and summaries
- Exporting data in various formats (JSON, CSV, TXT)
- Creating configuration files
- Logging important information

---

### 3. `list_directory(path=".")`
List contents of a directory with metadata.

**Parameters:**
- `path` (str, optional): Directory path (defaults to sandbox root)

**Returns:**
JSON with file listings, counts, total sizes

**Example Usage:**
```python
# Explore sandbox structure
listing = list_directory("data")
if listing["status"] == "success":
    for file_info in listing["files"]:
        print(f"{file_info['name']} ({file_info['type']}, {file_info['size']} bytes)")
```

**Common Use Cases:**
- Exploring available data files
- Checking if files exist before processing
- Getting file metadata and sizes
- Auditing file organization
- Finding files by pattern or type

---

### 4. `create_directory(path)`
Create a directory and any necessary parent directories.

**Parameters:**
- `path` (str): Directory path to create

**Returns:**
JSON with status and creation confirmation

**Example Usage:**
```python
# Organize files into categories
create_directory("reports/2024/january")
create_directory("data/raw")
create_directory("data/processed")
```

**Common Use Cases:**
- Organizing files into logical structures
- Preparing directories before saving files
- Creating project hierarchies
- Setting up data processing pipelines

---

### 5. `file_info(path)`
Get detailed metadata about a file or directory.

**Parameters:**
- `path` (str): Path to examine

**Returns:**
JSON with existence, type, size, timestamps, permissions, hash

**Example Usage:**
```python
# Check if a file exists and get its details
info = file_info("important_data.csv")
if info["exists"]:
    print(f"File size: {info['size']} bytes")
    print(f"Modified: {info['modified_time']}")
    print(f"SHA-256: {info['sha256']}")
```

**Common Use Cases:**
- Verifying file existence before operations
- Getting file checksums for integrity verification
- Monitoring file changes over time
- Debugging file access issues
- Checking file permissions and attributes

---

### 6. `delete_file(path)`
Safely delete a file from the sandbox.

**Parameters:**
- `path` (str): Path to file to delete

**Returns:**
JSON with status and space freed

**Example Usage:**
```python
# Clean up temporary files
cleanup_files = ["temp/processing.tmp", "temp/cache.dat"]
for file_path in cleanup_files:
    result = delete_file(file_path)
    if result["status"] == "success":
        print(f"Deleted {file_path}, freed {result['size_freed']} bytes")
```

**Common Use Cases:**
- Cleaning up temporary files
- Removing outdated data
- Managing disk space
- Implementing data retention policies

## 📋 Common Patterns and Examples

### Data Processing Pipeline

```python
# 1. Create organized directory structure
create_directory("data/raw")
create_directory("data/processed")
create_directory("reports")

# 2. Check for input data
input_info = file_info("data/raw/input.csv")
if not input_info["exists"]:
    print("Input file not found - please provide data")
    return

# 3. Process data (example)
raw_data = read_file("data/raw/input.csv")
if raw_data["status"] == "success":
    # Process the CSV data
    processed_data = process_csv_data(raw_data["content"])
    
    # Save processed results
    write_file("data/processed/cleaned_data.json", json.dumps(processed_data))
    
    # Generate summary report
    summary = create_summary_report(processed_data)
    write_file("reports/summary_report.md", summary)
    
    print("Data processing pipeline completed successfully")
```

### Multi-Agent Collaboration

```python
# Parent agent organizes shared workspace
create_directory("shared/tasks")
create_directory("shared/results")

# Create task files for clones
tasks = [
    {"id": 1, "type": "web_scraping", "url": "https://example1.com"},
    {"id": 2, "type": "web_scraping", "url": "https://example2.com"}
]

for i, task in enumerate(tasks):
    task_file = f"shared/tasks/task_{i+1}.json"
    write_file(task_file, json.dumps(task))

# Delegate tasks to clones
delegate(["Process task 1 from shared/tasks/task_1.json", 
          "Process task 2 from shared/tasks/task_2.json"])

# Later: Collect results from clones
results_listing = list_directory("shared/results")
for result_file in results_listing["files"]:
    if result_file["type"] == "file" and result_file["name"].endswith(".json"):
        result_data = read_file(f"shared/results/{result_file['name']}")
        # Aggregate results...
```

### Report Generation

```python
# Generate comprehensive analysis report
create_directory("reports/analysis")

# Collect data from various sources
web_data = extract_page_content()  # Web automation
analysis_results = analyze_data(web_data)

# Create multiple report formats
markdown_report = generate_markdown_report(analysis_results)
write_file("reports/analysis/report.md", markdown_report)

csv_data = convert_to_csv(analysis_results)
write_file("reports/analysis/data.csv", csv_data)

json_output = json.dumps(analysis_results, indent=2)
write_file("reports/analysis/results.json", json_output)

# Create index file linking all reports
index_content = f"""# Analysis Report Index

Generated: {datetime.now().isoformat()}

## Available Reports
- [Markdown Report](report.md)
- [CSV Data](data.csv) 
- [JSON Results](results.json)

## Summary
- Total data points: {len(analysis_results['data'])}
- Analysis completed: {analysis_results['completed']}
"""

write_file("reports/analysis/README.md", index_content)
```

### Configuration Management

```python
# Load and manage configuration settings
def load_config():
    config_info = file_info("config/settings.json")
    if config_info["exists"]:
        config_data = read_file("config/settings.json")
        return json.loads(config_data["content"])
    else:
        # Create default configuration
        default_config = {
            "max_retries": 3,
            "timeout": 30,
            "output_format": "json",
            "debug": False
        }
        create_directory("config")
        write_file("config/settings.json", json.dumps(default_config, indent=2))
        return default_config

def update_config(key, value):
    config = load_config()
    config[key] = value
    write_file("config/settings.json", json.dumps(config, indent=2))
    return config

# Usage
config = load_config()
if config["debug"]:
    print("Debug mode enabled")

# Update configuration
update_config("timeout", 60)
```

### Data Validation and Integrity

```python
# Implement data integrity checks
def verify_file_integrity(file_path, expected_hash=None):
    info = file_info(file_path)
    if not info["exists"]:
        return {"status": "error", "message": "File not found"}
    
    current_hash = info["sha256"]
    if expected_hash and current_hash != expected_hash:
        return {
            "status": "error", 
            "message": f"Hash mismatch. Expected: {expected_hash}, Got: {current_hash}"
        }
    
    return {"status": "success", "hash": current_hash, "size": info["size"]}

# Validate important data files
critical_files = ["data/customer_list.csv", "config/api_keys.json"]
for file_path in critical_files:
    validation = verify_file_integrity(file_path)
    if validation["status"] == "success":
        print(f"✓ {file_path} verified (Hash: {validation['hash'][:16]}...)")
    else:
        print(f"✗ {file_path} validation failed: {validation['message']}")
```

## 🚨 Error Handling Best Practices

### Always Check Status
```python
# Good: Always check operation status
result = read_file("data.txt")
if result["status"] == "success":
    content = result["content"]
    # Process content...
elif result["error_type"] == "file_not_found":
    print("File doesn't exist - creating default")
    write_file("data.txt", "default content")
else:
    print(f"Error reading file: {result['error_message']}")

# Bad: Assuming operations always succeed
content = read_file("data.txt")["content"]  # May fail!
```

### Graceful Degradation
```python
# Handle filesystem unavailability gracefully
def save_results(data, filename):
    try:
        result = write_file(filename, json.dumps(data))
        if result["status"] == "success":
            return {"saved": True, "location": filename}
    except Exception as e:
        print(f"Filesystem save failed: {e}")
    
    # Fallback: Save to group chat or return in response
    post_groupchat(f"Results (filesystem unavailable): {json.dumps(data)}")
    return {"saved": False, "data": data}
```

### Atomic Operations
```python
# Use atomic operations for critical data
def atomic_update(file_path, updater_function):
    # Read current data
    current = read_file(file_path)
    if current["status"] != "success":
        return {"status": "error", "message": "Failed to read current data"}
    
    # Apply updates
    try:
        updated_data = updater_function(current["content"])
    except Exception as e:
        return {"status": "error", "message": f"Update function failed: {e}"}
    
    # Write atomically (filesystem handles this internally)
    result = write_file(file_path, updated_data)
    return result

# Usage
def add_entry(data):
    entries = json.loads(data)
    entries.append({"timestamp": datetime.now().isoformat(), "event": "new_item"})
    return json.dumps(entries, indent=2)

atomic_update("logs/events.json", add_entry)
```

## 🎯 Best Practices

### File Organization
- **Use descriptive directory names**: `reports/2024/january` not `r/24/1`
- **Consistent file naming**: `analysis_YYYY-MM-DD.json`
- **Logical hierarchies**: Group related files together
- **Separate input/output**: Keep raw data separate from processed results

### Performance Optimization
- **Check file existence** before operations when uncertain
- **Use appropriate file formats**: JSON for structured data, CSV for tabular data
- **Clean up temporary files** to manage disk space
- **Batch operations** when possible to reduce overhead

### Security Considerations
- **Never hardcode sensitive data** in files - use configuration management
- **Validate file contents** before processing, especially from external sources
- **Use descriptive error messages** but avoid exposing system internals
- **Monitor file sizes** to prevent resource exhaustion

### Coordination with Other Agents
- **Use consistent file formats** across clones for interoperability
- **Document file structures** in README files for other agents
- **Implement file locking patterns** for shared resources when needed
- **Use status files** to coordinate complex multi-agent workflows

## 🔍 Troubleshooting

### Common Issues

**"Path resolves outside sandbox"**
- Cause: Attempted path traversal (`../`)
- Solution: Use relative paths within sandbox only

**"File extension 'xyz' not allowed"**
- Cause: File type not in whitelist
- Solution: Use permitted extensions (txt, md, json, csv, xml, html, py, yaml, log, etc.)

**"File size exceeds limit"**
- Cause: File larger than configured maximum
- Solution: Break large files into smaller chunks or compress data

**"Permission denied"**
- Cause: System-level file permissions issue
- Solution: Check sandbox directory permissions, may need system admin help

**"Encoding error"**
- Cause: File contains non-UTF-8 content
- Solution: Ensure all text files use UTF-8 encoding

### Debugging Techniques

```python
# Enable detailed error reporting
def debug_file_operation(operation, *args):
    print(f"Attempting {operation.__name__} with args: {args}")
    result = operation(*args)
    print(f"Result: {result}")
    return result

# Usage
result = debug_file_operation(read_file, "problematic_file.txt")
```

```python
# Check filesystem state
def filesystem_health_check():
    # Check sandbox accessibility
    root_listing = list_directory(".")
    print(f"Sandbox root accessible: {root_listing['status'] == 'success'}")
    
    # Check available space (estimate)
    test_file = "test_write_access.tmp"
    write_test = write_file(test_file, "test")
    if write_test["status"] == "success":
        delete_file(test_file)
        print("Write access: OK")
    else:
        print(f"Write access: FAILED - {write_test['error_message']}")
    
    # List any existing files
    if root_listing["status"] == "success":
        print(f"Files in sandbox: {root_listing['total_files']}")
        print(f"Directories in sandbox: {root_listing['total_directories']}")

filesystem_health_check()
```

## 🚀 Advanced Usage

### Streaming Large Files
```python
# Handle large datasets by processing in chunks
def process_large_csv(file_path, chunk_size=1000):
    file_data = read_file(file_path)
    if file_data["status"] != "success":
        return {"error": "Could not read file"}
    
    lines = file_data["content"].split('\n')
    header = lines[0]
    data_lines = lines[1:]
    
    results = []
    for i in range(0, len(data_lines), chunk_size):
        chunk = data_lines[i:i+chunk_size]
        chunk_data = header + '\n' + '\n'.join(chunk)
        
        # Process chunk
        processed = process_csv_chunk(chunk_data)
        results.extend(processed)
        
        # Save intermediate results
        chunk_file = f"processed_chunks/chunk_{i//chunk_size}.json"
        write_file(chunk_file, json.dumps(processed))
    
    return results
```

### File Versioning
```python
# Implement simple file versioning
def save_with_version(base_path, content):
    # Find next version number
    version = 1
    while True:
        version_path = f"{base_path}.v{version}"
        if not file_info(version_path)["exists"]:
            break
        version += 1
    
    # Save versioned file
    result = write_file(version_path, content)
    if result["status"] == "success":
        # Also save as "latest"
        write_file(f"{base_path}.latest", content)
        return {"version": version, "path": version_path}
    
    return {"error": "Failed to save"}

# Usage
save_with_version("reports/analysis", report_content)
```

### Filesystem-Based Task Queues
```python
# Implement simple task queue using filesystem
def create_task(task_data):
    task_id = f"task_{int(time.time())}_{random.randint(1000, 9999)}"
    task_file = f"queue/pending/{task_id}.json"
    
    create_directory("queue/pending")
    create_directory("queue/processing")
    create_directory("queue/completed")
    
    write_file(task_file, json.dumps(task_data))
    return task_id

def claim_next_task():
    pending = list_directory("queue/pending")
    if pending["status"] == "success" and pending["total_files"] > 0:
        task_file = pending["files"][0]["name"]
        task_path = f"queue/pending/{task_file}"
        
        # Move to processing
        task_data = read_file(task_path)
        if task_data["status"] == "success":
            write_file(f"queue/processing/{task_file}", task_data["content"])
            delete_file(task_path)
            return json.loads(task_data["content"])
    
    return None

def complete_task(task_id, result):
    processing_file = f"queue/processing/{task_id}.json"
    completed_file = f"queue/completed/{task_id}.json"
    
    # Read original task
    task_data = read_file(processing_file)
    if task_data["status"] == "success":
        task = json.loads(task_data["content"])
        task["result"] = result
        task["completed_at"] = datetime.now().isoformat()
        
        # Move to completed
        write_file(completed_file, json.dumps(task))
        delete_file(processing_file)
        return True
    
    return False
```

This comprehensive guide provides everything needed to effectively use KageBunshin's filesystem capabilities for complex automation tasks, data processing, and multi-agent coordination.