window.devDeleteFile = async function(path) {
  return new Promise((resolve, reject) => {
    window.resolveLocalFileSystemURL(path, (fileEntry) => {
      fileEntry.remove(
        () => resolve(true),    // succès
        (err) => reject(err)   // erreur
      )
    }, (err) => {
      // fichier non trouvé = on considère comme déjà supprimé
      if (err.code === 1) resolve(false)
      else reject(err)
    })
  })
}

window.devListDirectory = async function(path) {
    return new Promise((resolve, reject) => {
        window.resolveLocalFileSystemURL(path, (dirEntry) => {
            const reader = dirEntry.createReader()
            reader.readEntries((entries) => {
                resolve(entries) // tableau de FileEntry / DirectoryEntry
            }, reject)
        }, reject)
    })
}


window.devFileExists =async function(path) {
    return new Promise((resolve) => {
        window.resolveLocalFileSystemURL(
            path,
            () => resolve(true),
            () => resolve(false)
        );
    });
}

window.devReadFileContent = async function(path) {
  return new Promise((resolve, reject) => {
    window.resolveLocalFileSystemURL(path, (fileEntry) => {
      fileEntry.file((file) => {
        console.log('File object:', file)
        console.log('File size:', file.size)
        console.log('File type:', file.type)
        
        const reader = new FileReader()
        
        reader.onload = function(e) {
          console.log('onload fired, result:', this.result)
          console.log('result type:', typeof this.result)
          console.log('result length:', this.result ? this.result.length : 'N/A')
          resolve(this.result)
        }
        
        reader.onerror = function(e) {
          console.error('FileReader error:', e)
          reject(e)
        }
        
        reader.readAsText(file)
      }, (err) => {
        console.error('file() error:', err)
        reject(err)
      })
    }, (err) => {
      console.error('resolveLocalFileSystemURL error:', err)
      reject(err)
    })
  })
}
