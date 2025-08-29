# Filesystem Quick Examples

## 🚀 Quick Start Examples

### Basic File Operations
```python
# Save web scraping results
results = extract_page_content()
write_file("data/scraped_data.json", json.dumps(results))

# Read configuration
config = read_file("config/settings.json")
settings = json.loads(config["content"]) if config["status"] == "success" else {}

# List available data files
files = list_directory("data")
print(f"Found {files['total_files']} data files")
```

### Research and Analysis
```python
# Organize research findings
create_directory("research/sources")
create_directory("research/analysis")

# Save findings from each source
for i, url in enumerate(research_urls):
    data = extract_data_from_url(url)
    write_file(f"research/sources/source_{i+1}.md", data)

# Create analysis summary
analysis = analyze_all_sources()
write_file("research/analysis/summary.md", analysis)
```

### Multi-Agent Coordination
```python
# Parent agent: Setup shared workspace
create_directory("shared/tasks")
create_directory("shared/results")

# Create task files for clones
tasks = ["Analyze site A", "Analyze site B", "Analyze site C"]
for i, task in enumerate(tasks):
    write_file(f"shared/tasks/task_{i+1}.txt", task)

# Clone agent: Process assigned task
task_data = read_file("shared/tasks/task_1.txt")
result = process_task(task_data["content"])
write_file("shared/results/result_1.json", json.dumps(result))
```

### Report Generation
```python
# Generate comprehensive report
report_data = {
    "title": "Analysis Report",
    "date": datetime.now().isoformat(),
    "findings": collected_data
}

# Multiple formats
write_file("reports/analysis.json", json.dumps(report_data))
write_file("reports/analysis.md", generate_markdown_report(report_data))
write_file("reports/analysis.csv", convert_to_csv(report_data))
```

### Error Handling Pattern
```python
def safe_file_operation(operation, *args):
    try:
        result = operation(*args)
        if result["status"] == "success":
            return result
        else:
            print(f"Operation failed: {result.get('error_message', 'Unknown error')}")
            return None
    except Exception as e:
        print(f"Exception in file operation: {e}")
        return None

# Usage
data = safe_file_operation(read_file, "important_data.json")
if data:
    process_data(json.loads(data["content"]))
```

### Data Processing Pipeline
```python
# 1. Setup directories
create_directory("pipeline/input")
create_directory("pipeline/processing")
create_directory("pipeline/output")

# 2. Process data
input_files = list_directory("pipeline/input")
for file_info in input_files["files"]:
    if file_info["type"] == "file":
        # Read input
        raw_data = read_file(f"pipeline/input/{file_info['name']}")
        
        # Process
        processed = process_data(raw_data["content"])
        
        # Save output
        output_name = file_info["name"].replace(".raw", ".processed")
        write_file(f"pipeline/output/{output_name}", processed)
        
        # Archive input
        write_file(f"pipeline/processing/{file_info['name']}", raw_data["content"])
```

## 🛠️ Tool-Specific Examples

### read_file()
```python
# Load JSON configuration
config_result = read_file("config.json")
if config_result["status"] == "success":
    config = json.loads(config_result["content"])
    api_key = config.get("api_key")

# Read CSV data
csv_result = read_file("data.csv")
if csv_result["status"] == "success":
    lines = csv_result["content"].strip().split('\n')
    headers = lines[0].split(',')
    data = [dict(zip(headers, line.split(','))) for line in lines[1:]]
```

### write_file()
```python
# Save analysis results
results = {"score": 95, "insights": ["finding1", "finding2"]}
write_file("analysis_results.json", json.dumps(results, indent=2))

# Create markdown report
report = f"""# Analysis Report

## Summary
Analysis completed with score: {results['score']}

## Key Insights
{chr(10).join(f"- {insight}" for insight in results['insights'])}
"""
write_file("report.md", report)
```

### list_directory()
```python
# Find all JSON files
files = list_directory("data")
json_files = [f for f in files["files"] if f["name"].endswith(".json")]
print(f"Found {len(json_files)} JSON files")

# Check directory structure
for dir_name in ["input", "output", "archive"]:
    dir_info = list_directory(dir_name)
    if dir_info["status"] == "success":
        print(f"{dir_name}: {dir_info['total_files']} files")
```

### file_info()
```python
# Check if file exists and get size
info = file_info("large_dataset.csv")
if info["exists"]:
    if info["size"] > 1024 * 1024:  # 1MB
        print(f"Large file detected: {info['size']} bytes")
    print(f"Last modified: {info['modified_time']}")
else:
    print("File not found")
```

### create_directory()
```python
# Setup project structure
directories = [
    "data/raw",
    "data/processed", 
    "reports/daily",
    "reports/weekly",
    "config",
    "logs"
]

for directory in directories:
    result = create_directory(directory)
    print(f"Created {directory}: {result['status']}")
```

### delete_file()
```python
# Cleanup temporary files
temp_files = list_directory("temp")
if temp_files["status"] == "success":
    for file_info in temp_files["files"]:
        if file_info["name"].endswith(".tmp"):
            result = delete_file(f"temp/{file_info['name']}")
            if result["status"] == "success":
                print(f"Deleted {file_info['name']}, freed {result['size_freed']} bytes")
```

## 🔄 Common Workflows

### Web Scraping → Analysis → Report
```python
# 1. Scrape and save data
scraped_data = extract_page_content()
write_file("data/scraped.json", json.dumps(scraped_data))

# 2. Analyze data
analysis = analyze_scraped_data(scraped_data)
write_file("analysis/results.json", json.dumps(analysis))

# 3. Generate report
report = create_analysis_report(analysis)
write_file("reports/final_report.md", report)
```

### Multi-Source Data Collection
```python
# Setup
create_directory("sources")

# Collect from multiple sources
sources = ["site1.com", "site2.com", "site3.com"]
for i, source in enumerate(sources):
    data = scrape_source(source)
    write_file(f"sources/source_{i+1}_{source.replace('.', '_')}.json", json.dumps(data))

# Aggregate all sources
all_files = list_directory("sources")
combined_data = []
for file_info in all_files["files"]:
    if file_info["name"].endswith(".json"):
        source_data = read_file(f"sources/{file_info['name']}")
        combined_data.append(json.loads(source_data["content"]))

# Save combined dataset
write_file("combined_dataset.json", json.dumps(combined_data))
```

### Configuration-Driven Tasks
```python
# Load task configuration
config_data = read_file("task_config.json")
if config_data["status"] == "success":
    config = json.loads(config_data["content"])
    
    # Execute configured tasks
    for task in config["tasks"]:
        result = execute_task(task)
        
        # Save individual results
        write_file(f"results/{task['name']}_result.json", json.dumps(result))
    
    # Create summary
    summary = create_task_summary(config["tasks"])
    write_file("task_summary.md", summary)
```

### Backup and Versioning
```python
# Create timestamped backup
import datetime
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

# Backup important files
important_files = ["config.json", "data.csv", "results.json"]
create_directory(f"backups/{timestamp}")

for filename in important_files:
    file_data = read_file(filename)
    if file_data["status"] == "success":
        write_file(f"backups/{timestamp}/{filename}", file_data["content"])

print(f"Backup created: backups/{timestamp}")
```

## ⚡ Performance Tips

### Batch Operations
```python
# Process multiple files efficiently
files_to_process = list_directory("input")["files"]
results = []

for file_info in files_to_process:
    if file_info["type"] == "file":
        data = read_file(f"input/{file_info['name']}")
        if data["status"] == "success":
            processed = process_file_data(data["content"])
            results.append({"file": file_info["name"], "result": processed})

# Save all results at once
write_file("batch_results.json", json.dumps(results))
```

### Check Before Read/Write
```python
# Avoid unnecessary operations
def conditional_read(filepath):
    info = file_info(filepath)
    if info["exists"] and info["size"] > 0:
        return read_file(filepath)
    return {"status": "skipped", "reason": "File empty or missing"}

# Use for large files
data = conditional_read("potentially_large_file.csv")
if data["status"] == "success":
    process_data(data["content"])
```

### Memory-Efficient Processing
```python
# Process large files in chunks
def process_large_file(filepath):
    file_data = read_file(filepath)
    if file_data["status"] != "success":
        return
    
    lines = file_data["content"].split('\n')
    chunk_size = 1000
    
    for i in range(0, len(lines), chunk_size):
        chunk = lines[i:i+chunk_size]
        processed_chunk = process_lines(chunk)
        
        # Save intermediate results
        write_file(f"processed_chunks/chunk_{i//chunk_size}.txt", '\n'.join(processed_chunk))

# Combine chunks later
def combine_chunks():
    chunks = list_directory("processed_chunks")
    combined = []
    
    for chunk_file in sorted(chunks["files"], key=lambda x: x["name"]):
        chunk_data = read_file(f"processed_chunks/{chunk_file['name']}")
        combined.append(chunk_data["content"])
    
    write_file("final_result.txt", '\n'.join(combined))
```