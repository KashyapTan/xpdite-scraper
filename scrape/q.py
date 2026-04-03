import numpy as np

# Define the covariance matrix COV[X,X] as given in the problem
# COV[X,X] = A * D * A^T where:
# A = [[1/√2, 1/√2], [1/√2, -1/√2]]
# D = [[3, 0], [0, 1]]

sqrt_2 = np.sqrt(2)

# Matrix A
A = np.array([
    [1/sqrt_2, 1/sqrt_2],
    [1/sqrt_2, -1/sqrt_2]
])

# Diagonal matrix D
D = np.array([
    [3, 0],
    [0, 1]
])

# Compute the covariance matrix
COV = A @ D @ A.T

print("Covariance Matrix COV[X,X]:")
print(COV)
print()

# Find eigenvalues and eigenvectors of the covariance matrix
eigenvalues, eigenvectors = np.linalg.eig(COV)

print("Eigenvalues (variances in principal directions):")
print(eigenvalues)
print()

print("Eigenvectors (principal directions):")
print(eigenvectors)
print()

# Find the direction with smallest variance
min_variance_idx = np.argmin(eigenvalues)
min_variance = eigenvalues[min_variance_idx]
E_M = eigenvectors[:, min_variance_idx]

print("=" * 60)
print("SOLUTION:")
print("=" * 60)
print(f"Direction E_M with smallest variance:")
print(E_M)
print()
print(f"Smallest variance σ² = {min_variance}")
print()

# Normalize E_M to ensure it's a unit vector
E_M_normalized = E_M / np.linalg.norm(E_M)
print(f"Normalized E_M:")
print(E_M_normalized)
print()

# Check which answer matches
print("Checking against the given options:")
print()

options = [
    (np.array([1/sqrt_2, 1/sqrt_2]), 1, "Option 1"),
    (np.array([1/sqrt_2, 1/sqrt_2]), 3, "Option 2"),
    (np.array([1/sqrt_2, -1/sqrt_2]), 3, "Option 3"),
    (np.array([1/sqrt_2, -1/sqrt_2]), 1, "Option 4")
]

for vec, var, label in options:
    vec_match = np.allclose(np.abs(E_M_normalized), np.abs(vec))
    var_match = np.isclose(min_variance, var)
    if vec_match and var_match:
        print(f"✓ {label}: E_M = [{vec[0]:.4f}, {vec[1]:.4f}], σ² = {var} MATCHES!")
    else:
        print(f"✗ {label}: E_M = [{vec[0]:.4f}, {vec[1]:.4f}], σ² = {var}")
        if not vec_match:
            print(f"  Vector doesn't match (found {E_M_normalized})")
        if not var_match:
            print(f"  Variance doesn't match (found {min_variance})")
print()

# Verify by computing variance in the E_M direction
variance_check = E_M_normalized.T @ COV @ E_M_normalized
print(f"Verification - Variance in E_M direction: {variance_check}")
print(f"Should equal smallest eigenvalue: {min_variance}")
print(f"Match: {np.isclose(variance_check, min_variance)}")