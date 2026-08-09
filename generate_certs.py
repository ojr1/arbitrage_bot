from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import datetime

# Generate private key
key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

# Generate certificate
subject = issuer = x509.Name([
    x509.NameAttribute(NameOID.COUNTRY_NAME, "GB"),
    x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Research"),
    x509.NameAttribute(NameOID.COMMON_NAME, "betfair"),
])

cert = (
    x509.CertificateBuilder()
    .subject_name(subject)
    .issuer_name(issuer)
    .public_key(key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(datetime.datetime.utcnow())
    .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=3650))
    .sign(key, hashes.SHA256())
)

# Save key
with open("certs/client-2048.key", "wb") as f:
    f.write(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption()
    ))

# Save certificate
with open("certs/client-2048.crt", "wb") as f:
    f.write(cert.public_bytes(serialization.Encoding.PEM))

print("Certificates generated successfully")
print("certs/client-2048.key")
print("certs/client-2048.crt")