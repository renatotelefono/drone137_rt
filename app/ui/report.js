document.querySelectorAll('[data-time]').forEach(button => {
  button.addEventListener('click', () => {
    const video = document.getElementById('video');
    video.currentTime = Number(button.dataset.time);
    video.play().catch(() => {});
    video.scrollIntoView({behavior: 'smooth', block: 'center'});
  });
});
