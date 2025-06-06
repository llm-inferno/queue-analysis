
# Start from golang base image
FROM golang:alpine AS builder

# Update
RUN apk update

# Set the working directory in the container
WORKDIR /app

# Copy go mod and sum files
COPY go.mod go.sum ./

# Download and install dependencies
RUN go mod download

# Copy the project files to the working directory
COPY . .

# Build the Go binary
RUN go build -o ./bin/main .

# Start a new stage from scratch
FROM scratch

# Copy the Pre-built binary file
COPY --from=builder /app/bin/main .

# Expose the port the API will listen on
EXPOSE 8080

# Command to run the binary when the container starts
CMD ["./main"]