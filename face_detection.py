import cv2
cap = cv2.VideoCapture(0)
while(True):
    #读取摄像头当前这一帧的画面  ret:True fase image:当前这一帧画面
    ret, img = cap.read()
    #图片进行灰度处理
    img_flipped = cv2.flip(img, 1)
    gray = cv2.cvtColor(img_flipped,cv2.COLOR_BGR2GRAY)
    

    cv2.imshow('face',img_flipped)
    if cv2.waitKey(20) & 0XFF == ord('q'):
        break
cap.release()
cv2.destroyAllWindows()