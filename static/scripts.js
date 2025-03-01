// scripts.js 完整代码
let mediaStream = null;
let mediaRecorder;
let recordedChunks = [];
let isRecording = false;
let selectedFileName = null;
let realtimeAnalyzer = null;
let standardKeypoints = null;


// 元素引用
const videoPreview = document.getElementById('videoPreview');
const uploadList = document.getElementById('uploadList');

// 按钮事件绑定
document.getElementById('openCamera').addEventListener('click', openCamera);
document.getElementById('closeCamera').addEventListener('click', closeCamera);
document.getElementById('startRecord').addEventListener('click', startRecording);
document.getElementById('stopRecord').addEventListener('click', stopRecording);
document.getElementById('uploadVideo').addEventListener('click', uploadVideo);
document.getElementById('analyzeVideo').addEventListener('click', analyzeVideo);
document.getElementById('realtimeAnalyze').addEventListener('click', realtimeAnalyze);
// 在现有事件监听部分添加
document.getElementById('refreshList').addEventListener('click', () => loadFileList());

// 初始化加载文件列表
loadFileList();

async function openCamera() {
    try {
        mediaStream = await navigator.mediaDevices.getUserMedia({ 
            video: {
                width: { ideal: 640 },
                height: { ideal: 480 }
            }
        });
        videoPreview.srcObject = mediaStream;
        videoPreview.play();
    } catch (error) {
        console.error('摄像头访问失败:', error);
        alert('无法访问摄像头，请检查权限和连接');
    }
}

function closeCamera() {
    if (mediaStream) {
        mediaStream.getTracks().forEach(track => track.stop());
        mediaStream = null;
        videoPreview.srcObject = null;
    }
}

// scripts.js 修改录制部分
async function startRecording() {
    if (!mediaStream) {
        alert('请先打开摄像头！');
        return;
    }
    
    try {
        // 强制使用MP4编码（H.264）
        const mimeType = 'video/mp4; codecs=avc1';
        
        if (!MediaRecorder.isTypeSupported(mimeType)) {
            throw new Error('当前浏览器不支持MP4录制，请使用Chrome或Edge浏览器');
        }

        mediaRecorder = new MediaRecorder(mediaStream, { mimeType });
        
        mediaRecorder.ondataavailable = event => {
            if (event.data.size > 0) {
                recordedChunks.push(event.data);
            }
        };
        
        mediaRecorder.onstop = async () => {
            const blob = new Blob(recordedChunks, { type: mimeType });
            await sendVideoToServer(blob);
            recordedChunks = [];
        };
        
        mediaRecorder.start(200);
        isRecording = true;
        updateButtonStates();
    } catch (error) {
        alert(error.message);
    }
}

function stopRecording() {
    if (mediaRecorder && isRecording) {
        mediaRecorder.stop();
        isRecording = false;
        updateButtonStates();
    }
}

// scripts.js 修改发送到服务器的部分
async function sendVideoToServer(blob) {
    try {
        // 强制使用.mp4后缀
        const filename = `recording_${Date.now()}.mp4`;
        const file = new File([blob], filename, { type: 'video/mp4' });
        
        const formData = new FormData();
        formData.append('video', file);
        
        const response = await fetch('/upload', {
            method: 'POST',
            body: formData
        });
        
        if (response.ok) {
            alert('视频已成功保存！');
            loadFileList();
        } else {
            throw new Error(`上传失败：${response.statusText}`);
        }
    } catch (error) {
        alert(error.message);
    }
}

function uploadVideo() {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'video/mp4, video/webm, video/avi';
    
    input.onchange = async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        const formData = new FormData();
        formData.append('video', file);

        try {
            const response = await fetch('/upload', {
                method: 'POST',
                body: formData
            });
            
            if (response.ok) {
                alert('上传成功！');
                loadFileList();
            } else {
                const error = await response.json();
                throw new Error(error.error || '上传失败');
            }
        } catch (error) {
            alert(error.message);
        }
    };
    
    input.click();
}

function updateButtonStates() {
    document.getElementById('startRecord').disabled = isRecording;
    document.getElementById('stopRecord').disabled = !isRecording;
    document.getElementById('openCamera').disabled = isRecording;
}

function loadFileList() {
    fetch('/uploads')
        .then(response => response.json())
        .then(files => {
            uploadList.innerHTML = files.map(file => 
                `<div class="file-item" onclick="selectFile('${file.name.replace(/'/g, "\\'")}')">
                    ${file.name}
                    <button onclick="downloadFile('${file.name.replace(/'/g, "\\'")}')">下载</button>
                </div>`
            ).join('');
        });
}

function downloadFile(filename) {
    window.open(`/download/${filename}`, '_blank');
}
function selectFile(filename) {
    selectedFileName = filename;
    // 高亮选中项
    document.querySelectorAll('.file-item').forEach(item => {
        item.classList.remove('selected');
    });
    event.currentTarget.classList.add('selected');
}

async function analyzeVideo() {
    if (!selectedFileName) {
        alert('请先选择要分析的视频');
        return;
    }
    
    try {
        const response = await fetch('/analyze', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                filename: selectedFileName
            })
        });
        
        const result = await response.json();
        if (response.ok) {
            alert('分析完成！结果视频已生成');
            loadFileList();  // 刷新文件列表
        } else {
            throw new Error(result.error || '分析失败');
        }
    } catch (error) {
        alert(error.message);
    }
}
async function loadStandardKeypoints() {

}
async function realtimeAnalyze() {
    
}
function drawAnalysisOverlay(ctx, keypoints, videoWidth, videoHeight) {
    
}

// 停止实时分析
function stopRealtimeAnalyze() {
    
}