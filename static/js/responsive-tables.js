// Responsive Table Helper
// Automatically adds data-label attributes to table cells for mobile view

document.addEventListener('DOMContentLoaded', () => {
    const responsiveTables = document.querySelectorAll('.table-responsive-mobile table');

    responsiveTables.forEach(table => {
        const headers = Array.from(table.querySelectorAll('thead th')).map(th => th.textContent.trim());

        table.querySelectorAll('tbody tr').forEach(row => {
            const cells = row.querySelectorAll('td');
            cells.forEach((cell, index) => {
                if (headers[index]) {
                    cell.setAttribute('data-label', headers[index]);
                }
            });
        });
    });
});
