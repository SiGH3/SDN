#!/bin/bash
# Comprehensive test script for NS-3 routing performance comparison

echo "=========================================="
echo "NS-3 Routing Performance Testing"
echo "=========================================="
echo ""

echo "Test 1: 3-Cluster Scenario (C1→C3)"
echo "-----------------------------------"
python3 performance_comparison.py --scenario 3_cluster --src 1 --dst 3 --time 1
echo ""

echo "Test 2: 5-Cluster Scenario (C1→C4)"
echo "-----------------------------------"
python3 performance_comparison.py --scenario 5_cluster --src 1 --dst 4 --time 1
echo ""

echo "Test 3: All Scenarios with Graphs"
echo "-----------------------------------"
python3 performance_comparison.py --all --time 1
echo ""

echo "Test 4: Custom Weights (Delay-Sensitive)"
echo "-----------------------------------"
python3 performance_comparison.py --scenario 5_cluster --src 1 --dst 4 --alpha 0.5 --beta 0.2 --gamma 0.3
echo ""

echo "=========================================="
echo "All tests completed!"
echo "Check generated files:"
echo "  - performance_comparison.png"
echo "  - improvement_comparison.png"
echo "=========================================="
