from cut_flv import cut_file
import sys,os

time_length = 60*1000

def list_all_file(root_path):
    result = []
    ext_des = 'py'
    list = os.listdir(root_path)
    for i in range(0,len(list)):
        path = os.path.join(root_path,list[i])
        #print('test ',path)
        if os.path.isfile(path) and (path.split('.')[-1] == ext_des):
            result.append(path)
    return result

def start_cuting(file_name):
    srcFileName, ext=os.path.splitext(file_name) 
    print('srcFileName:',srcFileName,'ext:',ext)

if __name__ == '__main__':
    #cut_file('D:\\test\\1\\123.flv', 'D:\\test\\2\\123.flv', 10000, 20000)
    cur_file_path = os.path.dirname(os.path.realpath(__file__))
    tar_file_path = cur_file_path + '\\result'
    print('cur_file_path :',cur_file_path,'\ntar_file_path :',tar_file_path)
    file_list = list_all_file(cur_file_path)
    [start_cuting(x) for x in file_list]