document.addEventListener('DOMContentLoaded', function() {
    // Initialize voting functionality
    const voteButtons = document.querySelectorAll('.vote-btn');
    voteButtons.forEach(button => {
        button.addEventListener('click', function() {
            const post = this.closest('.post');
            const voteCount = post.querySelector('.vote-count');
            const currentCount = parseInt(voteCount.textContent);
            
            if (this.classList.contains('upvote')) {
                voteCount.textContent = currentCount + 1;
            } else if (this.classList.contains('downvote')) {
                voteCount.textContent = currentCount - 1;
            }
        });
    });

    // Initialize map if on detail page
    if (document.getElementById('map')) {
        initMap();
    }

    // Add smooth scrolling for anchor links
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function(e) {
            e.preventDefault();
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                target.scrollIntoView({
                    behavior: 'smooth'
                });
            }
        });
    });
});

// Google Maps initialization
function initMap() {
    const mapElement = document.getElementById('map');
    const lat = parseFloat(mapElement.dataset.lat);
    const lng = parseFloat(mapElement.dataset.lng);

    const map = new google.maps.Map(mapElement, {
        center: { lat: lat, lng: lng },
        zoom: 15
    });

    new google.maps.Marker({
        position: { lat: lat, lng: lng },
        map: map,
        title: 'Crime Location'
    });
} 