#!/bin/bash
# Script to generate Python code from Protocol Buffer definitions
#
# This script compiles .proto files into Python code that can be used
# by the gRPC client and server.
#
# Usage: ./generate_grpc_code.sh

set -e  # Exit on error

echo "🔧 gRPC Code Generator"
echo "====================="
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/../../../.." && pwd )"

echo "📁 Script directory: $SCRIPT_DIR"
echo "📁 Project root: $PROJECT_ROOT"
echo ""

# Check if grpcio-tools is installed
echo "🔍 Checking dependencies..."
if ! python -c "import grpc_tools" 2>/dev/null; then
    echo -e "${RED}❌ grpcio-tools is not installed${NC}"
    echo ""
    echo "Please install it using one of these methods:"
    echo "  pip install grpcio grpcio-tools"
    echo "  poetry add grpcio grpcio-tools"
    exit 1
fi

echo -e "${GREEN}✅ grpcio-tools is installed${NC}"
echo ""

# Create generated directory if it doesn't exist
GENERATED_DIR="$SCRIPT_DIR/generated"
echo "📂 Creating generated code directory..."
mkdir -p "$GENERATED_DIR"

# Create __init__.py in generated directory
if [ ! -f "$GENERATED_DIR/__init__.py" ]; then
    echo '"""Generated gRPC code"""' > "$GENERATED_DIR/__init__.py"
    echo -e "${GREEN}✅ Created __init__.py${NC}"
fi

# Find all .proto files in the current directory
PROTO_FILES=$(find "$SCRIPT_DIR" -maxdepth 1 -name "*.proto")

if [ -z "$PROTO_FILES" ]; then
    echo -e "${YELLOW}⚠️  No .proto files found in $SCRIPT_DIR${NC}"
    echo "Please create a .proto file first (you can use example_service.proto as reference)"
    exit 1
fi

echo "📝 Found .proto files:"
for proto in $PROTO_FILES; do
    echo "   - $(basename $proto)"
done
echo ""

# Generate Python code for each .proto file
echo "🚀 Generating Python code..."
echo ""

for PROTO_FILE in $PROTO_FILES; do
    PROTO_NAME=$(basename "$PROTO_FILE")
    echo "Processing: $PROTO_NAME"
    
    # Run the protoc compiler
    python -m grpc_tools.protoc \
        -I"$SCRIPT_DIR" \
        --python_out="$GENERATED_DIR" \
        --grpc_python_out="$GENERATED_DIR" \
        "$PROTO_FILE"
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ Successfully generated code for $PROTO_NAME${NC}"
        
        # Show generated files
        BASE_NAME="${PROTO_NAME%.proto}"
        echo "   Generated files:"
        echo "   - ${BASE_NAME}_pb2.py (message classes)"
        echo "   - ${BASE_NAME}_pb2_grpc.py (service stub)"
    else
        echo -e "${RED}❌ Failed to generate code for $PROTO_NAME${NC}"
        exit 1
    fi
    echo ""
done

echo ""
echo -e "${GREEN}🎉 Code generation complete!${NC}"
echo ""
echo "📚 Next steps:"
echo "1. Import the generated code in your client:"
echo "   from inline_agents.backends.openai.grpc.generated import example_service_pb2"
echo "   from inline_agents.backends.openai.grpc.generated import example_service_pb2_grpc"
echo ""
echo "2. Initialize the stub in client.py:"
echo "   self.stub = example_service_pb2_grpc.OpenAIServiceStub(self.channel)"
echo ""
echo "3. Create message requests:"
echo "   request = example_service_pb2.MessageRequest("
echo "       message='Hello',"
echo "       project_uuid='123'"
echo "   )"
echo ""
echo "4. Call RPC methods:"
echo "   response = self.stub.SendMessage(request)"
echo ""

