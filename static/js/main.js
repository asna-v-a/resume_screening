// Global selected files tracker
let selectedFiles = [];

document.addEventListener("DOMContentLoaded", function () {
    const dropZone = document.getElementById("drop-zone");
    const fileInput = document.getElementById("file-input");
    const filesList = document.getElementById("files-list");
    const filesQueueContainer = document.getElementById("files-queue-container");
    const fileCountSpan = document.getElementById("file-count");
    const uploadForm = document.getElementById("upload-form");

    if (dropZone && fileInput) {
        // Drag-and-drop events
        ["dragenter", "dragover"].forEach(eventName => {
            dropZone.addEventListener(eventName, (e) => {
                e.preventDefault();
                e.stopPropagation();
                dropZone.classList.add("drag-over");
            }, false);
        });

        ["dragleave", "drop"].forEach(eventName => {
            dropZone.addEventListener(eventName, (e) => {
                e.preventDefault();
                e.stopPropagation();
                dropZone.classList.remove("drag-over");
            }, false);
        });

        dropZone.addEventListener("drop", (e) => {
            const dt = e.dataTransfer;
            const files = dt.files;
            handleFilesSelect(files);
        });

        dropZone.addEventListener("click", () => {
            fileInput.click();
        });

        fileInput.addEventListener("change", function () {
            handleFilesSelect(this.files);
        });
    }

    // Handles adding files to the local queue
    function handleFilesSelect(files) {
        for (let i = 0; i < files.length; i++) {
            const file = files[i];
            const ext = file.name.split('.').pop().toLowerCase();
            
            // Check file type
            if (!["pdf", "docx", "txt"].includes(ext)) {
                alert(`File format .${ext} is not supported. Please upload PDF, DOCX or TXT files.`);
                continue;
            }
            
            // Avoid duplicate files in queue
            if (selectedFiles.some(f => f.name === file.name && f.size === file.size)) {
                continue;
            }

            selectedFiles.push(file);
        }

        updateFilesQueueUI();
    }

    // Renders the visual queue of selected files
    function updateFilesQueueUI() {
        if (!filesList) return;
        
        filesList.innerHTML = "";
        
        if (selectedFiles.length > 0) {
            filesQueueContainer.style.display = "block";
            fileCountSpan.textContent = selectedFiles.length;
            
            selectedFiles.forEach((file, index) => {
                const fileItem = document.createElement("div");
                fileItem.className = "file-item fade-in";
                
                // Get human readable size
                const sizeKB = (file.size / 1024).toFixed(1);
                const sizeDisplay = sizeKB > 1024 ? `${(sizeKB / 1024).toFixed(1)} MB` : `${sizeKB} KB`;
                
                // Set file icon
                let iconClass = "fa-file-lines";
                const ext = file.name.split('.').pop().toLowerCase();
                if (ext === "pdf") iconClass = "fa-file-pdf text-danger";
                else if (ext === "docx") iconClass = "fa-file-word text-primary";
                
                fileItem.innerHTML = `
                    <div class="file-item-info">
                        <i class="fa-solid ${iconClass}"></i>
                        <span class="file-item-name" title="${file.name}">${file.name}</span>
                        <span class="file-item-size">(${sizeDisplay})</span>
                    </div>
                    <button type="button" class="file-item-remove" data-index="${index}">
                        <i class="fa-solid fa-xmark"></i>
                    </button>
                `;
                
                filesList.appendChild(fileItem);
            });
            
            // Attach delete click listeners
            document.querySelectorAll(".file-item-remove").forEach(button => {
                button.addEventListener("click", function(e) {
                    e.stopPropagation();
                    const index = parseInt(this.getAttribute("data-index"));
                    selectedFiles.splice(index, 1);
                    updateFilesQueueUI();
                });
            });
        } else {
            filesQueueContainer.style.display = "none";
            fileCountSpan.textContent = "0";
        }
    }

    // Intercept form submission to handle sequential uploader
    if (uploadForm) {
        uploadForm.addEventListener("submit", function (e) {
            e.preventDefault();

            const jobTitle = document.getElementById("job-title").value.trim();
            const jobDesc = document.getElementById("job-description").value.trim();

            if (!jobTitle || !jobDesc) {
                alert("Please fill out the Job Title and Job Description fields.");
                return;
            }

            if (selectedFiles.length === 0) {
                alert("Please select at least one resume file to screen.");
                return;
            }

            // Show progress overlay
            const loaderOverlay = document.getElementById("loader-overlay");
            const progressBar = document.getElementById("processing-progress");
            const loaderStatus = document.getElementById("loader-status");
            
            loaderOverlay.style.display = "flex";
            progressBar.style.width = "0%";
            loaderStatus.textContent = "Saving Job Description details...";

            // Step 1: Save Job Description (always creates a new unique session)
            let jdId = null;
            const jdData = new FormData();
            jdData.append("job_title", jobTitle);
            jdData.append("job_description", jobDesc);
            
            const saveJdPromise = fetch("/api/save-jd", {
                method: "POST",
                body: jdData
            }).then(response => {
                if (!response.ok) throw new Error("Could not create screening session.");
                return response.json();
            });

            saveJdPromise
                .then(data => {
                    if (!data.success) throw new Error(data.error || "Failed to save JD.");
                    
                    jdId = data.jd_id;
                    return uploadResumesSequentially(jdId, selectedFiles, progressBar, loaderStatus);
                })
                .then(jdId => {
                    loaderStatus.textContent = "Success! Redirecting to rankings...";
                    progressBar.style.width = "100%";
                    setTimeout(() => {
                        window.location.href = `/dashboard?jd_id=${jdId}`;
                    }, 800);
                })
                .catch(error => {
                    loaderOverlay.style.display = "none";
                    alert(`Error screening resumes: ${error.message}`);
                });
        });
    }

    // Sequentially uploads each resume in the queue using AJAX
    async function uploadResumesSequentially(jdId, files, progressBar, loaderStatus) {
        const total = files.length;
        
        for (let i = 0; i < total; i++) {
            const file = files[i];
            const percent = Math.round((i / total) * 100);
            progressBar.style.width = `${percent}%`;
            loaderStatus.textContent = `Processing resume ${i + 1} of ${total}: ${file.name}...`;

            const formData = new FormData();
            formData.append("jd_id", jdId);
            formData.append("resume", file);

            try {
                const response = await fetch("/api/upload-resume", {
                    method: "POST",
                    body: formData
                });
                
                if (!response.ok) {
                    const errData = await response.json();
                    throw new Error(errData.error || `Upload failed for ${file.name}`);
                }
                
                const result = await response.json();
                if (!result.success) {
                    throw new Error(result.error || `Processing failed for ${file.name}`);
                }
            } catch (err) {
                console.error(err);
                if (!confirm(`Failed to process ${file.name}: ${err.message}. Continue with remaining files?`)) {
                    throw new Error("Screening cancelled by user.");
                }
            }
        }
        
        progressBar.style.width = "100%";
        return jdId;
    }
});
