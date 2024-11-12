import requests
import healing_agent
import socket

@healing_agent
def test_api_call():
    """Test function that makes a buggy DNS lookup that will fail and need healing"""
    print("♣ Attempting DNS lookup...")
    
    # Intentionally incorrect DNS query setup
    # Using wrong port and protocol for DNS lookup
    dns_server = "8.8.8.8"  # Google's DNS
    dns_port = 80  # Wrong port (should be 53)
    
    # Creating TCP socket instead of UDP
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2)
    
    # Trying to send malformed DNS query
    query = b"VALID_DNS_QUERY"
    sock.connect((dns_server, dns_port))
    sock.send(query)
    
    # Trying to parse response without proper DNS protocol handling
    response = sock.recv(512)
    domain_name = response.decode('utf-8')
    
    return domain_name

if __name__ == "__main__":
    try:
        result = test_api_call()
        print(f"♣ DNS Response: {result}")
    except Exception as e:
        print(f"♣ Test completed with expected error: {str(e)}")


