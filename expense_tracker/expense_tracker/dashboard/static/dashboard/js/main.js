document.addEventListener('DOMContentLoaded', function() {
    // Expenses Over Time Line Chart
    const ctxLine = document.getElementById('expensesOverTime').getContext('2d');
    new Chart(ctxLine, {
        type: 'line',
        data: timeData,
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    grid: {
                        display: true,
                        color: '#f1f5f9'
                    },
                    ticks: {
                        callback: function(value) {
                            return currencySymbol + ' ' + value/1000 + 'k';
                        }
                    }
                },
                x: {
                    grid: {
                        display: false
                    }
                }
            }
        }
    });

    // Expenses by Category Donut Chart
    const ctxDonut = document.getElementById('expensesByCategory').getContext('2d');
    new Chart(ctxDonut, {
        type: 'doughnut',
        data: categoryData,
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '80%',
            plugins: {
                legend: {
                    display: false
                }
            }
        }
    });

    // Monthly Budget Progress Donut Chart
    const ctxBudget = document.getElementById('monthlyBudgetProgress').getContext('2d');
    new Chart(ctxBudget, {
        type: 'doughnut',
        data: {
            labels: ['Used', 'Remaining'],
            datasets: [{
                data: [budgetPercent, 100 - budgetPercent],
                backgroundColor: ['#5470ff', '#f1f5f9'],
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '85%',
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    enabled: false
                }
            }
        }
    });
});
