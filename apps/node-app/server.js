const http = require("http");

const PORT = 8000;

const server = http.createServer((req, res) => {
    res.setHeader("Content-Type", "application/json");

    if (req.url === "/health") {
        res.writeHead(200);
        res.end(JSON.stringify({
            status: "healthy",
            version: "1.0"
        }));
        return;
    }

    res.writeHead(200);
    res.end(JSON.stringify({
        message: "Hello from Node.js deployment",
        version: "1.0"
    }));
});

server.listen(PORT, "0.0.0.0", () => {
    console.log(`Node.js app running on port ${PORT}`);
});
