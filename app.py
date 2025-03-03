from flask import Flask, render_template, send_from_directory, jsonify, request,send_file,Response
from werkzeug.utils import secure_filename
import os
import process
import cv2
from ultralytics import YOLO
import numpy as np
import json
from flask_cors import CORS  # 新增跨域支持
import base64

app = Flask(__name__)
CORS(app)  # 允许跨域请求

app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'mp4', 'webm', 'avi'}
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.environ["WERKZEUG_RUN_MAIN"] = "false"  # 禁用部分重载逻辑

STANDARD_KP_PATH = "keypoints/aligned1.json"
with open(STANDARD_KP_PATH, 'r') as f:
    STANDARD_KEYPOINTS = json.load(f)

model = YOLO(os.path.join("models", "yolo11n-pose.pt"))

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/uploads', methods=['GET'])
def list_uploads():
    try:
        files = []
        for filename in os.listdir(app.config['UPLOAD_FOLDER']):
            path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            if os.path.isfile(path):
                files.append({'name': filename})
        return jsonify(files)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/upload', methods=['POST'])
def handle_upload():
    if 'video' not in request.files:
        return jsonify({'error': '未选择文件'}), 400
        
    file = request.files['video']
    if file.filename == '':
        return jsonify({'error': '无效文件名'}), 400
        
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        return jsonify({'status': 'success', 'filename': filename}), 200
        
    return jsonify({'error': '文件类型不允许'}), 400

@app.route('/analyze', methods=['POST'])
def handle_analysis():
    if not request.json or 'filename' not in request.json:
        return jsonify({'error': '未选择文件'}), 400
    
    try:
        # 路径配置
        user_filename = request.json['filename']
        user_video = os.path.join(app.config['UPLOAD_FOLDER'], user_filename)
        
        # 定义处理路径（直接使用原文件名+后缀）
        base_name = os.path.splitext(user_filename)[0]
        # app.py中分析视频的路径配置
        paths = {
            "video1_path": "movies/1.mp4",
            "video2_path": user_video,
            "output_vid1_path": "uploads/1_process.mp4",  # 标准视频处理结果
            "output_vid2_path": f"uploads/{base_name}_处理.mp4",
            "keypoints1_path": "keypoints/aligned1.json",     # 标准关键点固定路径
            "keypoints2_path": f"keypoints/{base_name}_kp.json",
            "overlay_path": f"uploads/{base_name}_叠加.mp4"
        }
        
        # 执行处理流程
        process.process_pose_videos(
            paths["video1_path"], 
            paths["video2_path"],
            paths["output_vid1_path"],
            paths["output_vid2_path"],
            paths["keypoints1_path"],
            paths["keypoints2_path"]
        )
        
        process.align_keypoints(
            paths["keypoints1_path"],
            paths["keypoints2_path"],
            paths["keypoints1_path"],  # 覆盖原关键点文件
            paths["keypoints2_path"]
        )
        
        # 计算相似度
        resolution = (640, 360)
        weights = [0.2,0.5,0.5,0.7,0.7,0.6,0.6,0.7,0.7,0.6,0.6,0,0,0,0,0,0]
        
        similarity_scores, _ = process.calculate_similarity_and_low_similarity_frames(
            paths["keypoints1_path"],
            paths["keypoints2_path"],
            resolution,
            weights
        )
        
        # 生成叠加视频
        process.generate_overlay_video(
            paths["output_vid1_path"],
            paths["output_vid2_path"],
            similarity_scores,
            paths["overlay_path"]
        )
        
        return jsonify({
            'status': 'success',
            'overlay': f"{base_name}_overlay.mp4"  # 直接返回文件名
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/process_frame', methods=['POST'])
def process_frame():
    try:
        # 接收Base64编码的图片
        data = request.json
        image_data = base64.b64decode(data['image'].split(',')[1])
        nparr = np.frombuffer(image_data, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        # 处理帧（使用process.py中的逻辑）
        processed_frame = process.process_single_frame(
            frame=frame,
            standard_kp_json=STANDARD_KEYPOINTS,
            model=model,
            frame_index=0,  # 实时模式不需要帧索引
            weights=[0.2,0.5,0.5,0.7,0.7,0.6,0.6,0.7,0.7,0.6,0.6,0,0,0,0,0,0],
            resolution=(640, 480)
        )
        
        # 编码返回图片
        _, buffer = cv2.imencode('.jpg', processed_frame)
        return jsonify({
            'processed': base64.b64encode(buffer).decode('utf-8')
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download/<path:filename>')  # 使用path转换器支持斜杠和特殊字符
def download_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)


if __name__ == '__main__':
    app.run(debug=False, port=5000,use_reloader=False)